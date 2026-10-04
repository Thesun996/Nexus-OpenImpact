"""Frontend request/response assumptions and deliberately closed CORS."""

from hashlib import sha256
import io
import json
from pathlib import Path
import zipfile

from fastapi.testclient import TestClient
import pytest

from openimpact.api import app

DEMO = Path(__file__).resolve().parents[1] / "examples" / "signature_change"
INSPECT = "/api/v1/projects/inspect"
VALIDATE = "/api/v1/changes/validate"
ANALYZE = "/api/v1/projects/analyze"
CHANGE = {"target_symbol_id": "utils.format_date",
          "added_parameter": {"name": "timezone", "kind": "positional_or_keyword"}}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    with TestClient(app) as client:
        yield client


@pytest.fixture
def upload():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DEMO.glob("*.py")):
            archive.writestr(path.name, path.read_bytes())
    return buffer.getvalue()


def form_post(client, path, upload, change=CHANGE, fingerprint=None):
    data = {}
    if path != INSPECT:
        data["change"] = change if isinstance(change, str) else json.dumps(change)
        if fingerprint is not None:
            data["expected_fingerprint"] = fingerprint
    return client.post(path, data=data, files={"file": ("project.zip", upload, "application/zip")})


def test_health_and_cross_origin_remain_closed_pending_confirmation(client):
    # Synthetic test origin, unrelated to any member's server or deployment.
    origin = "https://frontend.example.test"
    health = client.get("/api/v1/health", headers={"Origin": origin})
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "version": "0.1.0"}
    assert "access-control-allow-origin" not in health.headers
    preflight = client.options(ANALYZE, headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert preflight.status_code == 405
    assert "access-control-allow-origin" not in preflight.headers


def test_browser_form_contract_and_evidence_explanation_mapping(client, upload):
    inspected = form_post(client, INSPECT, upload)
    assert inspected.status_code == 200
    body = inspected.json()
    fingerprint = body["project_fingerprint"]
    assert fingerprint == sha256(upload).hexdigest()
    assert set(body) == {"project_name", "project_fingerprint", "source_root", "modules",
                         "symbols", "coverage", "diagnostics"}
    target = next(symbol for symbol in body["symbols"] if symbol["symbol_id"] == CHANGE["target_symbol_id"])
    assert target["parameters"][0]["name"] == "date"
    validated = form_post(client, VALIDATE, upload, fingerprint=fingerprint)
    assert validated.status_code == 200
    assert validated.json()["project_fingerprint"] == fingerprint
    assert validated.json()["validation"] == {"valid": True, "diagnostics": []}
    analyzed = form_post(client, ANALYZE, upload, fingerprint=fingerprint)
    assert analyzed.status_code == 200
    report = analyzed.json()
    assert report["change"] == validated.json()["change_spec"]
    assert report["schema_version"] == 1
    assert report["project_path"] == "."
    assert report["coverage"]["status"] == "complete"
    assert [report["summary"][name] for name in (
        "direct_impact_count", "indirect_1hop_count", "indirect_2hop_count"
    )] == [1, 1, 1]
    assert len(report["evidences"]) == len(report["explanations"]) == (
        len(report["direct_impacts"]) + len(report["indirect_impacts"])
    )
    assert [entry["evidence"] for entry in report["explanations"]] == report["evidences"]
    direct = report["direct_impacts"][0]
    evidence = report["evidences"][0]
    assert "evidence_reference" not in direct
    assert evidence["target_symbol"] == direct["target_symbol_id"]
    assert [evidence["location"][key] for key in ("file", "line", "column")] == [
        direct[key] for key in ("file", "line", "column")
    ]
    for index, finding in enumerate(report["indirect_impacts"], start=len(report["direct_impacts"])):
        evidence = report["evidences"][index]
        assert evidence["impact_type"] == finding["impact_type"]
        assert evidence["propagation_path"][0]["symbols"][0] == finding["impacted_symbol_id"]
        assert evidence["propagation_path"][0]["direct_evidence_reference"] == (
            report["evidences"][0]["evidence_reference"]
        )
    assert all(entry["explanation"]["risk_level"] == "unknown" for entry in report["explanations"])
    assert not any("provider_used" in entry or "fallback_reason" in entry for entry in report["explanations"])


@pytest.mark.parametrize("path", [INSPECT, VALIDATE, ANALYZE])
def test_json_body_does_not_replace_required_multipart(client, path):
    response = client.post(path, json=CHANGE)
    assert response.status_code == 422
    assert set(response.json()) == {"detail"}


def test_three_error_shapes_match_handoff(client, upload):
    invalid_zip = form_post(client, INSPECT, b"not zip")
    assert invalid_zip.status_code == 400
    assert invalid_zip.json()["error"]["code"] == "invalid_zip"
    invalid_change = form_post(client, VALIDATE, upload, change="{")
    assert invalid_change.status_code == 422
    assert invalid_change.json()["validation"]["valid"] is False
    assert invalid_change.json()["change_spec"] is None
    assert invalid_change.json()["validation"]["diagnostics"][0]["code"] == "invalid_change_json"
    missing = client.post(ANALYZE)
    assert missing.status_code == 422
    assert set(missing.json()) == {"detail"}
    mismatch = form_post(client, ANALYZE, upload, fingerprint="0" * 64)
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "fingerprint_mismatch"
