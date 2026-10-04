"""Frozen three-step backend flow and uploaded-response safety checks."""

import hashlib
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from openimpact.analysis.ast_parser import ASTParser
from openimpact.analysis.models import ParseDiagnostic, ParsedModule
from openimpact.api import app
from openimpact.repository import zip_inspector

DEMO = Path(__file__).resolve().parents[1] / "examples" / "signature_change"
CHANGE = {"target_symbol_id": "utils.format_date",
          "added_parameter": {"name": "timezone", "kind": "positional_or_keyword"}}


def demo_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DEMO.iterdir()):
            if path.is_file():
                info = zipfile.ZipInfo(f"signature_change/{path.name}", (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                data = path.read_bytes()
                if path.suffix in {".py", ".json"}:
                    # This frozen demo fixture uses Git's LF source bytes regardless
                    # of checkout EOLs. Production ZIP fingerprints still hash the
                    # exact uploaded bytes; possible binary fixtures stay unchanged.
                    data = data.replace(b"\r\n", b"\n")
                archive.writestr(info, data)
    return buffer.getvalue()


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"], ids=["lf", "crlf"])
def test_frozen_demo_zip_is_stable_across_checkout_line_endings(tmp_path, monkeypatch, newline):
    for path in DEMO.iterdir():
        if path.is_file():
            data = path.read_bytes()
            if path.suffix in {".py", ".json"}:
                data = data.replace(b"\r\n", b"\n").replace(b"\n", newline)
            (tmp_path / path.name).write_bytes(data)
    monkeypatch.setitem(demo_zip.__globals__, "DEMO", tmp_path)
    samples = Path(__file__).resolve().parents[1] / "docs" / "api-samples"
    captured = json.loads((samples / "inspect-response.json").read_text(encoding="utf-8"))

    assert hashlib.sha256(demo_zip()).hexdigest() == captured["project_fingerprint"]


def submit(client, path: str, data: bytes, fingerprint: str | None = None):
    fields = {"change": json.dumps(CHANGE)}
    if fingerprint is not None:
        fields["expected_fingerprint"] = fingerprint
    return client.post(path, data=fields,
                       files={"file": ("signature_change.zip", data, "application/zip")})


def test_three_step_flow_keeps_fingerprint_and_cleans_each_request():
    data = demo_zip()
    fingerprint = hashlib.sha256(data).hexdigest()
    original_directory = zip_inspector.TemporaryDirectory
    locations: list[Path] = []

    def record_directory(*args, **kwargs):
        directory = original_directory(*args, **kwargs)
        locations.append(Path(directory.name))
        return directory

    with patch.object(zip_inspector, "TemporaryDirectory", side_effect=record_directory), TestClient(app) as client:
        inspected = client.post(
            "/api/v1/projects/inspect",
            files={"file": ("signature_change.zip", data, "application/zip")},
        )
        assert inspected.status_code == 200
        assert inspected.json()["project_fingerprint"] == fingerprint
        assert "utils.format_date" in {item["symbol_id"] for item in inspected.json()["symbols"]}
        validated = submit(client, "/api/v1/changes/validate", data, fingerprint)
        assert validated.status_code == 200
        assert validated.json()["project_fingerprint"] == fingerprint
        assert validated.json()["validation"]["valid"] is True
        analyzed = submit(client, "/api/v1/projects/analyze", data, fingerprint)

    assert analyzed.status_code == 200
    body = analyzed.json()
    assert body["change"] == validated.json()["change_spec"]
    assert body["summary"]["direct_impact_count"] == 1
    assert body["summary"]["indirect_1hop_count"] == 1
    assert body["summary"]["indirect_2hop_count"] == 1
    assert body["coverage"]["status"] == "complete"
    assert body["project_path"] == "."
    assert len(locations) == 3 and all(not location.exists() for location in locations)
    assert all(str(location) not in response.text
               for location in locations for response in (inspected, validated, analyzed))


def test_changed_zip_with_old_fingerprint_stops_before_index_or_analysis():
    original = demo_zip()
    changed = original + b"changed trailing bytes"
    with (patch.object(zip_inspector, "TemporaryDirectory") as temporary,
          patch("openimpact.api.analyze_project") as analysis,
          TestClient(app) as client):
        response = submit(client, "/api/v1/projects/analyze", changed,
                          hashlib.sha256(original).hexdigest())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "fingerprint_mismatch"
    temporary.assert_not_called()
    analysis.assert_not_called()


def test_uploaded_read_and_encoding_diagnostics_hide_temporary_paths():
    data = demo_zip()
    original_parse = ASTParser.parse

    def diagnostic_parse(self):
        if self.path.name == "page.py":
            return ParsedModule(self.path, (), (), (), (
                ParseDiagnostic("read_error", f"could not read {self.path}"),
            ))
        if self.path.name == "dashboard.py":
            return ParsedModule(self.path, (), (), (), (
                ParseDiagnostic("encoding_error", f"encoding failure {self.path}"),
            ))
        return original_parse(self)

    with patch.object(ASTParser, "parse", diagnostic_parse), TestClient(app) as client:
        inspected = client.post(
            "/api/v1/projects/inspect",
            files={"file": ("demo.zip", data, "application/zip")},
        )
        validated = submit(client, "/api/v1/changes/validate", data)
        analyzed = submit(client, "/api/v1/projects/analyze", data)
    for response in (inspected, validated, analyzed):
        assert response.status_code == 200
        assert "openimpact-zip-" not in response.text
        errors = response.json()["diagnostics"]["parse_errors"]
        assert {item["file"] for item in errors} == {"page.py", "dashboard.py"}
        assert all(not Path(item["file"]).is_absolute() for item in errors)
        assert {item["message"] for item in errors} == {
            "无法读取项目源文件。", "项目源文件编码无法解析。"
        }
    assert analyzed.json()["coverage"]["status"] == "partial"


def test_checked_in_http_samples_match_the_frozen_contract(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    data = demo_zip()
    samples = Path(__file__).resolve().parents[1] / "docs" / "api-samples"

    def captured(name):
        return json.loads((samples / name).read_text(encoding="utf-8"))

    with TestClient(app) as client:
        inspected = client.post(
            "/api/v1/projects/inspect",
            files={"file": ("signature_change.zip", data, "application/zip")},
        )
        fingerprint = inspected.json()["project_fingerprint"]
        validated = submit(client, "/api/v1/changes/validate", data, fingerprint)
        analyzed = submit(client, "/api/v1/projects/analyze", data, fingerprint)
        rejected = submit(client, "/api/v1/projects/analyze", data + b"changed", "0" * 64)

    assert inspected.json() == captured("inspect-response.json")
    assert validated.json() == captured("validate-response.json")
    assert analyzed.json() == captured("analyze-response.json")
    assert rejected.status_code == 409
    assert rejected.json() == captured("error-response.json")
