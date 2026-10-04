"""Optional change_type preserves the existing multipart and report contract."""

import hashlib
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from openimpact.api import app

DEMO = Path(__file__).resolve().parents[1] / "examples" / "signature_change"


def demo_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DEMO.glob("*.py")):
            archive.writestr(f"signature_change/{path.name}", path.read_bytes())
    return buffer.getvalue()


def config(**extra):
    return {"target_symbol_id": "utils.format_date",
            "added_parameter": {"name": "timezone", "kind": "positional_or_keyword"}, **extra}


def submit(client, path, archive, change, fingerprint):
    return client.post(path, files={"file": ("project.zip", archive, "application/zip")},
                       data={"change": json.dumps(change), "expected_fingerprint": fingerprint})


def test_old_and_explicit_add_requests_have_identical_validate_and_analyze_responses(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    data = demo_zip()
    with TestClient(app) as client:
        inspected = client.post("/api/v1/projects/inspect",
            files={"file": ("project.zip", data, "application/zip")})
        assert inspected.status_code == 200
        fingerprint = inspected.json()["project_fingerprint"]
        assert fingerprint == hashlib.sha256(data).hexdigest()
        validated = None
        for route in ("/api/v1/changes/validate", "/api/v1/projects/analyze"):
            old = submit(client, route, data, config(), fingerprint)
            explicit = submit(client, route, data, config(change_type="add_required_parameter"), fingerprint)
            assert old.status_code == explicit.status_code == 200
            assert explicit.json() == old.json()
            body = old.json()
            if route.endswith("validate"):
                assert body["project_fingerprint"] == fingerprint
                validated = body["change_spec"]
                assert set(validated) == {"change_type", "target_symbol_id", "before", "after", "added_parameter"}
            else:
                assert body["change"] == validated
                assert body["schema_version"] == 1
                assert (body["summary"]["direct_impact_count"],
                        body["summary"]["indirect_1hop_count"],
                        body["summary"]["indirect_2hop_count"]) == (1, 1, 1)
                assert body["coverage"]["status"] == "complete"
                assert body["evidences"][0]["rule"] == "required_parameter_added_breaks_call"
                assert len(body["evidences"]) == len(body["explanations"]) == 3


@pytest.mark.parametrize("change_type", ["unsupported_change", "rename_parameter", None, [], 42])
@pytest.mark.parametrize("route", ["/api/v1/changes/validate", "/api/v1/projects/analyze"])
def test_unregistered_or_invalid_change_types_do_not_enter_analysis(change_type, route):
    data = demo_zip()
    with patch("openimpact.api.analyze_project") as analysis, TestClient(app) as client:
        response = submit(client, route, data, config(change_type=change_type),
                          hashlib.sha256(data).hexdigest())
    assert response.status_code == 422
    assert response.json()["validation"]["valid"] is False
    assert response.json()["validation"]["diagnostics"][0]["code"] == "invalid_change_config"
    assert response.json()["change_spec"] is None
    analysis.assert_not_called()
