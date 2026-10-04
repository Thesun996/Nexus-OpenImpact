"""Same ZIP endpoints validate and analyze removal without weakening safety checks."""

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
from test_backend_stability import live_backend  # Reuse the bounded real-TCP server fixture.

DEMO = Path(__file__).resolve().parents[1] / "examples" / "parameter_removal"
ROUTES = ("/api/v1/changes/validate", "/api/v1/projects/analyze")


@pytest.fixture(autouse=True)
def rule_mode(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")


def archive(files=None):
    if files is None:
        files = {path.name: path.read_bytes() for path in DEMO.glob("*.py")}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipped:
        for name, source in sorted(files.items()):
            zipped.writestr(name, source)
    return buffer.getvalue()


def config(name="timezone", target="utils.format_date", **extra):
    return {"change_type": "remove_parameter", "target_symbol_id": target,
            "parameter_name": name, **extra}


def submit(client, route, data, change=None, fingerprint=None):
    change = config() if change is None else change
    fields = {"change": change if isinstance(change, str) else json.dumps(change),
              "expected_fingerprint": fingerprint or sha256(data).hexdigest()}
    return client.post(route, files={"file": ("project.zip", data, "application/zip")}, data=fields)


def test_remove_http_three_step_workflow_matches_core_and_cleans_snapshots():
    data = archive()
    original_directory = zip_inspector.TemporaryDirectory
    locations = []

    def record_directory(*args, **kwargs):
        directory = original_directory(*args, **kwargs)
        locations.append(Path(directory.name))
        return directory

    with patch.object(zip_inspector, "TemporaryDirectory", side_effect=record_directory), TestClient(app) as client:
        inspected = client.post("/api/v1/projects/inspect",
            files={"file": ("project.zip", data, "application/zip")})
        fingerprint = inspected.json()["project_fingerprint"]
        assert fingerprint == sha256(data).hexdigest()
        symbol = next(item for item in inspected.json()["symbols"] if item["symbol_id"] == "utils.format_date")
        assert [p["name"] for p in symbol["parameters"]] == ["date", "timezone"]
        validated = submit(client, ROUTES[0], data, fingerprint=fingerprint)
        analyzed = submit(client, ROUTES[1], data, fingerprint=fingerprint)
    assert [response.status_code for response in (inspected, validated, analyzed)] == [200, 200, 200]
    spec = validated.json()["change_spec"]
    assert validated.json()["project_fingerprint"] == fingerprint
    assert spec["change_type"] == "remove_parameter"
    assert spec["operation"] == {"change_type": "remove_parameter", "parameter_name": "timezone"}
    assert spec["added_parameter"] is None
    assert [p["name"] for p in spec["after"]["parameters"]] == ["date"]
    expected = build_report(analyze_project(DEMO, load_change_spec(DEMO / "change.json")))
    expected["project_path"] = "."
    assert analyzed.json() == expected
    assert analyzed.json()["change"] == spec
    assert len(locations) == 3 and all(not location.exists() for location in locations)
    for response in (inspected, validated, analyzed):
        assert all(str(location) not in response.text for location in locations)
        assert "openimpact-zip-" not in response.text


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("source,change,code", [
    ("def f(a, b): pass\n", config("missing", "utils.f"), "parameter_not_found"),
    ("def f(a, *args): pass\n", config("args", "utils.f"), "unsupported_parameter_kind"),
    ("def f(a, **kwargs): pass\n", config("kwargs", "utils.f"), "unsupported_parameter_kind"),
    ("def f(a, b): pass\n", config("b", "missing.f"), "target_not_found"),
    ("def f(a, b): pass\n", config("bad name", "utils.f"), "invalid_operation_payload"),
])
def test_remove_validation_errors_are_422_and_never_analyzed(route, source, change, code):
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
    assert response.json()["validation"] == {"valid": False, "diagnostics": [
        {"code": code, "message": response.json()["validation"]["diagnostics"][0]["message"]}]}
    assert response.json()["change_spec"] is None
    analysis.assert_not_called()
    assert locations and all(not path.exists() for path in locations)


@pytest.mark.parametrize("change", [
    {"change_type": "remove_parameter", "target_symbol_id": "utils.format_date"},
    config(insert_before="date"),
    config(added_parameter={"name": "extra", "kind": "keyword_only"}),
    config(change_type="rename_parameter"),
    {"target_symbol_id": "utils.format_date", "parameter_name": "timezone"},
])
def test_cross_type_payloads_are_rejected_without_guessing(change):
    with patch("openimpact.api.analyze_project") as analysis, TestClient(app) as client:
        response = submit(client, ROUTES[1], archive(), change)
    assert response.status_code == 422
    assert response.json()["validation"]["diagnostics"][0]["code"] == "invalid_change_config"
    analysis.assert_not_called()


@pytest.mark.parametrize("route", ROUTES)
def test_remove_fingerprint_mismatch_stops_before_extracting_or_analysis(route):
    original = archive()
    changed = archive({"utils.py": "def format_date(date, timezone, mode): pass\n"})
    with (patch.object(zip_inspector, "TemporaryDirectory") as temporary,
          patch("openimpact.api.analyze_project") as analysis, TestClient(app) as client):
        response = submit(client, route, changed, fingerprint=sha256(original).hexdigest())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "fingerprint_mismatch"
    temporary.assert_not_called()
    analysis.assert_not_called()


def test_remove_partial_coverage_retains_known_impacts_and_relative_diagnostics():
    files = {path.name: path.read_bytes() for path in DEMO.glob("*.py")}
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


def test_remove_validation_and_analysis_never_change_uploaded_source():
    data = archive()
    original = data[:]
    with zipfile.ZipFile(io.BytesIO(data)) as zipped:
        source = zipped.read("utils.py")
    checks = []

    def observe_validation(index, spec):
        path = index.scanner.project_path / "utils.py"
        checks.append(path.read_bytes())
        result = validate_change_spec(index, spec)
        checks.append(path.read_bytes())
        return result

    with patch("openimpact.api.validate_change_spec", side_effect=observe_validation), TestClient(app) as client:
        assert submit(client, ROUTES[0], data).status_code == 200
        assert submit(client, ROUTES[1], data).status_code == 200
    assert checks == [source] * 4
    assert data == original


def test_remove_zero_impact_comes_from_the_actual_uploaded_project():
    data = archive({"utils.py": "def f(a, b=2): pass\n",
                    "caller.py": "from utils import f\ndef caller():\n    f(1)\n"})
    with TestClient(app) as client:
        response = submit(client, ROUTES[1], data, config("b", "utils.f"))
    assert response.status_code == 200
    body = response.json()
    assert body["change"]["target_symbol_id"] == "utils.f"
    assert body["summary"]["direct_impact_count"] == 0
    assert body["summary"]["indirect_1hop_count"] == body["summary"]["indirect_2hop_count"] == 0
    assert body["direct_impacts"] == body["indirect_impacts"] == body["evidences"] == body["explanations"] == []
    assert body["coverage"]["status"] == "complete"


def test_remove_real_http_workflow_and_cleanup(live_backend):
    client, _, locations = live_backend
    data = archive()
    inspected = client.post("/api/v1/projects/inspect",
        files={"file": ("project.zip", data, "application/zip")})
    assert inspected.status_code == 200
    fingerprint = inspected.json()["project_fingerprint"]
    validated = submit(client, ROUTES[0], data, fingerprint=fingerprint)
    analyzed = submit(client, ROUTES[1], data, fingerprint=fingerprint)
    assert validated.status_code == analyzed.status_code == 200
    body = analyzed.json()
    assert body["change"] == validated.json()["change_spec"]
    assert body["change"]["operation"]["parameter_name"] == "timezone"
    assert body["summary"]["direct_impact_count"] == 1
    assert body["summary"]["indirect_1hop_count"] == 1
    assert body["summary"]["indirect_2hop_count"] == 1
    assert body["coverage"]["status"] == "complete"
    assert len(body["evidences"]) == len(body["explanations"]) == 3
    assert "删除参数 timezone" in body["explanations"][0]["explanation"]["why_affected"]
    assert len(locations) == 3 and all(not location.exists() for location in locations)
    assert "openimpact-zip-" not in analyzed.text
    assert client.get("/api/v1/health").status_code == 200
