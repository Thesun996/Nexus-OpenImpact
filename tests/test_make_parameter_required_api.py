"""Existing ZIP endpoints validate and analyze removing an existing default."""

from hashlib import sha256
import io
import json
from pathlib import Path
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
import pytest

from openimpact.analysis.change_file import load_change_spec
from openimpact.analysis.change_spec import validate_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.api import app
from openimpact.repository import zip_inspector
from test_backend_stability import live_backend  # Reuse bounded real-TCP server and cleanup checks.

ROOT = Path(__file__).resolve().parents[1]
ROUTES = ("/api/v1/changes/validate", "/api/v1/projects/analyze")


@pytest.fixture(autouse=True)
def rule_mode(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")


def archive(files=None, mode="missing"):
    if files is None:
        demo = ROOT / "examples" / f"parameter_required_{mode}"
        files = {path.name: path.read_bytes() for path in demo.glob("*.py")}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipped:
        for name, source in sorted(files.items()):
            zipped.writestr(name, source)
    return buffer.getvalue()


def config(name="timeout", target="utils.connect", **extra):
    return {"change_type": "make_parameter_required", "target_symbol_id": target,
            "parameter_name": name, **extra}


def submit(client, route, data, change=None, fingerprint=None):
    change = config() if change is None else change
    fields = {"change": change if isinstance(change, str) else json.dumps(change),
              "expected_fingerprint": fingerprint or sha256(data).hexdigest()}
    return client.post(route, files={"file": ("project.zip", data, "application/zip")}, data=fields)


@pytest.mark.parametrize("mode,count", [("missing", 1), ("explicit", 0)])
def test_make_required_http_workflow_matches_core_and_cleans_snapshots(mode, count):
    data = archive(mode=mode)
    original_directory = zip_inspector.TemporaryDirectory
    locations = []

    def record_directory(*args, **kwargs):
        directory = original_directory(*args, **kwargs)
        locations.append(Path(directory.name))
        return directory

    with patch.object(zip_inspector, "TemporaryDirectory", side_effect=record_directory), TestClient(app) as client:
        inspected = client.post("/api/v1/projects/inspect",
            files={"file": ("project.zip", data, "application/zip")})
        assert inspected.status_code == 200
        fingerprint = inspected.json()["project_fingerprint"]
        assert fingerprint == sha256(data).hexdigest()
        symbol = next(s for s in inspected.json()["symbols"] if s["symbol_id"] == "utils.connect")
        assert symbol["parameters"][1]["has_default"] is True
        validated = submit(client, ROUTES[0], data, fingerprint=fingerprint)
        analyzed = submit(client, ROUTES[1], data, fingerprint=fingerprint)
    assert validated.status_code == analyzed.status_code == 200
    assert validated.json()["project_fingerprint"] == fingerprint
    spec = validated.json()["change_spec"]
    assert spec["operation"] == {"change_type": "make_parameter_required", "parameter_name": "timeout"}
    assert spec["added_parameter"] is None
    assert spec["before"]["parameters"][1]["has_default"] is True
    assert spec["before"]["parameters"][1]["default_source"] == "30"
    assert spec["after"]["parameters"][1]["has_default"] is False
    assert spec["after"]["parameters"][1]["default_source"] is None
    demo = ROOT / "examples" / f"parameter_required_{mode}"
    expected = build_report(analyze_project(demo, load_change_spec(demo / "change.json")))
    expected["project_path"] = "."
    assert analyzed.json() == expected
    assert analyzed.json()["change"] == spec
    assert analyzed.json()["schema_version"] == 1
    assert analyzed.json()["coverage"]["status"] == "complete"
    for key in ("direct_impact_count", "indirect_1hop_count", "indirect_2hop_count"):
        assert analyzed.json()["summary"][key] == count
    assert len(locations) == 3 and all(not location.exists() for location in locations)
    for response in (inspected, validated, analyzed):
        assert all(str(location) not in response.text for location in locations)
        assert "openimpact-zip-" not in response.text


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("source,change,code", [
    ("def f(a, timeout=30): pass\n", config("missing", "utils.f"), "parameter_not_found"),
    ("def f(a, timeout): pass\n", config("timeout", "utils.f"), "parameter_already_required"),
    ("def f(a, *args): pass\n", config("args", "utils.f"), "unsupported_parameter_kind"),
    ("def f(a, **kwargs): pass\n", config("kwargs", "utils.f"), "unsupported_parameter_kind"),
    ("def f(a=1, timeout=30): pass\n", config("timeout", "utils.f"), "invalid_after_signature"),
    ("def f(a=1, /, timeout=30): pass\n", config("timeout", "utils.f"), "invalid_after_signature"),
    ("def f(a, timeout=30): pass\n", config("timeout", "missing.f"), "target_not_found"),
])
def test_make_required_errors_are_422_cleanup_and_never_analyzed(route, source, change, code):
    data = archive({"utils.py": source})
    original_directory = zip_inspector.TemporaryDirectory
    locations = []

    def record_directory(*args, **kwargs):
        directory = original_directory(*args, **kwargs)
        locations.append(Path(directory.name))
        return directory

    with (patch.object(zip_inspector, "TemporaryDirectory", side_effect=record_directory),
          patch("openimpact.api.analyze_project") as analysis, TestClient(app) as client):
        response = submit(client, route, data, change)
    assert response.status_code == 422
    body = response.json()
    assert body["validation"]["valid"] is False
    assert body["validation"]["diagnostics"][0]["code"] == code
    assert body["change_spec"] is None
    analysis.assert_not_called()
    assert locations and all(not path.exists() for path in locations)
    assert "openimpact-zip-" not in response.text


@pytest.mark.parametrize("literal", ["None", "False", "0", "''"])
def test_falsy_defaults_are_optional_before_and_required_after_http_validation(literal):
    data = archive({"utils.py": f"def f(timeout={literal}): pass\n",
        "caller.py": "from utils import f\ndef caller():\n    f()\n"})
    with TestClient(app) as client:
        validated = submit(client, ROUTES[0], data, config("timeout", "utils.f"))
        analyzed = submit(client, ROUTES[1], data, config("timeout", "utils.f"))
    assert validated.status_code == analyzed.status_code == 200
    spec = validated.json()["change_spec"]
    assert spec["before"]["parameters"][0]["has_default"] is True
    assert spec["before"]["parameters"][0]["default_source"] == literal
    assert spec["after"]["parameters"][0]["has_default"] is False
    assert spec["after"]["parameters"][0]["default_source"] is None
    assert analyzed.json()["summary"]["direct_impact_count"] == 1


@pytest.mark.parametrize("change", [
    {"change_type": "make_parameter_required", "target_symbol_id": "utils.connect"},
    config(added_parameter={"name": "other", "kind": "keyword_only"}),
    config(insert_before="address"), config(default=None),
    config(new_parameter_name="delay"),
    {"target_symbol_id": "utils.connect", "parameter_name": "timeout"},
    config(change_type="make_parameter_optional"),
])
def test_make_required_payload_is_explicit_and_does_not_accept_other_operations(change):
    with patch("openimpact.api.analyze_project") as analysis, TestClient(app) as client:
        response = submit(client, ROUTES[1], archive(), change)
    assert response.status_code == 422
    assert response.json()["validation"]["diagnostics"][0]["code"] == "invalid_change_config"
    analysis.assert_not_called()


@pytest.mark.parametrize("route", ROUTES)
def test_make_required_fingerprint_mismatch_stops_before_extraction(route):
    original = archive()
    changed = archive({"utils.py": "def connect(address, timeout=60): pass\n"})
    with (patch.object(zip_inspector, "TemporaryDirectory") as temporary,
          patch("openimpact.api.analyze_project") as analysis, TestClient(app) as client):
        response = submit(client, route, changed, fingerprint=sha256(original).hexdigest())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "fingerprint_mismatch"
    temporary.assert_not_called()
    analysis.assert_not_called()


def test_make_required_partial_coverage_retains_known_impacts_and_safe_diagnostics():
    demo = ROOT / "examples" / "parameter_required_missing"
    files = {path.name: path.read_bytes() for path in demo.glob("*.py")}
    files["broken.py"] = b"def bad(:\n"
    with TestClient(app) as client:
        response = submit(client, ROUTES[1], archive(files))
    assert response.status_code == 200
    body = response.json()
    assert body["coverage"]["status"] == "partial"
    assert body["coverage"]["message"]
    assert body["summary"]["direct_impact_count"] == 1
    assert body["diagnostics"]["parse_errors"][0]["file"] == "broken.py"
    assert "openimpact-zip-" not in response.text


def test_make_required_never_executes_default_expressions_or_changes_source():
    source = b"raise RuntimeError('uploaded code must not execute')\ndef f(a, timeout=unknown_default()): return a\n"
    data = archive({"utils.py": source})
    checks = []

    def observe_validation(index, spec):
        path = index.scanner.project_path / "utils.py"
        checks.append(path.read_bytes())
        assert spec.before.parameters[1].default_source == "unknown_default()"
        result = validate_change_spec(index, spec)
        checks.append(path.read_bytes())
        return result

    with patch("openimpact.api.validate_change_spec", side_effect=observe_validation), TestClient(app) as client:
        assert submit(client, ROUTES[0], data, config("timeout", "utils.f")).status_code == 200
        assert submit(client, ROUTES[1], data, config("timeout", "utils.f")).status_code == 200
    assert checks == [source] * 4


def test_keyword_only_metadata_default_order_and_star_manual_review_survive_http():
    data = archive({"utils.py": "async def f(a: str = 'x', *, timeout: int = 30) -> str: return a\n",
        "caller.py": "from utils import f\ndef caller(payload):\n    f()\n    f(timeout=10)\n    f(**payload)\n"})
    with TestClient(app) as client:
        validated = submit(client, ROUTES[0], data, config("timeout", "utils.f"))
        analyzed = submit(client, ROUTES[1], data, config("timeout", "utils.f"))
    assert validated.status_code == analyzed.status_code == 200
    spec = validated.json()["change_spec"]
    assert spec["after"]["is_async"] is True
    assert spec["after"]["return_annotation_source"] == "str"
    assert spec["before"]["parameters"][0] == spec["after"]["parameters"][0]
    assert spec["after"]["parameters"][1] == {"name": "timeout", "kind": "keyword_only",
        "has_default": False, "default_source": None, "annotation_source": "int"}
    body = analyzed.json()
    assert body["summary"]["direct_impact_count"] == body["summary"]["manual_review_count"] == 1
    assert body["manual_reviews"][0]["before_status"] == body["manual_reviews"][0]["after_status"] == "manual_review"
    assert body["indirect_impacts"] == []


def test_make_required_real_http_both_demos_stale_fingerprint_and_illegal_signature(live_backend):
    client, _, locations = live_backend
    fingerprints = []
    for mode, count in (("missing", 1), ("explicit", 0)):
        data = archive(mode=mode)
        inspected = client.post("/api/v1/projects/inspect",
            files={"file": ("project.zip", data, "application/zip")})
        assert inspected.status_code == 200
        fingerprint = inspected.json()["project_fingerprint"]
        fingerprints.append(fingerprint)
        assert fingerprint == sha256(data).hexdigest()
        validated = submit(client, ROUTES[0], data, fingerprint=fingerprint)
        analyzed = submit(client, ROUTES[1], data, fingerprint=fingerprint)
        assert validated.status_code == analyzed.status_code == 200
        body = analyzed.json()
        assert body["change"] == validated.json()["change_spec"]
        assert body["change"]["operation"]["change_type"] == "make_parameter_required"
        for key in ("direct_impact_count", "indirect_1hop_count", "indirect_2hop_count"):
            assert body["summary"][key] == count
        assert body["coverage"]["status"] == "complete"
        assert len(body["evidences"]) == len(body["explanations"]) == 3 * count
        if count:
            assert "移除原有默认值" in body["evidences"][0]["reason"]
            assert body["evidences"][0]["call_expression"] == "connect(address)"
        else:
            assert body["direct_impacts"] == body["indirect_impacts"] == body["evidences"] == body["explanations"] == []
        assert "openimpact-zip-" not in analyzed.text
    assert fingerprints[0] != fingerprints[1]
    mismatch = submit(client, ROUTES[1], archive(mode="explicit"), fingerprint=fingerprints[0])
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "fingerprint_mismatch"
    illegal = archive({"utils.py": "def f(a=1, timeout=30): pass\n"})
    rejected = submit(client, ROUTES[1], illegal, config("timeout", "utils.f"))
    assert rejected.status_code == 422
    assert rejected.json()["validation"]["diagnostics"][0]["code"] == "invalid_after_signature"
    assert len(locations) == 7 and all(not location.exists() for location in locations)
    assert client.get("/api/v1/health").status_code == 200
