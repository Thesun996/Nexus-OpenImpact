"""HTTP endpoints for persisted analysis reports."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from openimpact.api import app

DEMO = Path(__file__).resolve().parents[1] / "examples" / "signature_change"
CHANGE = {
    "target_symbol_id": "utils.format_date",
    "added_parameter": {"name": "timezone", "kind": "positional_or_keyword"},
}


def demo_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DEMO.iterdir()):
            if path.is_file():
                archive.writestr(f"signature_change/{path.name}", path.read_bytes())
    return buffer.getvalue()


def test_analyze_and_save_report_then_list_and_read(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENIMPACT_DB_PATH", str(tmp_path / "openimpact.sqlite3"))
    data = demo_zip()
    fingerprint = hashlib.sha256(data).hexdigest()
    fields = {"change": json.dumps(CHANGE), "expected_fingerprint": fingerprint}

    with TestClient(app) as client:
        saved = client.post(
            "/api/v1/reports",
            data=fields,
            files={"file": ("signature_change.zip", data, "application/zip")},
        )
        listed = client.get("/api/v1/reports")

    assert saved.status_code == 200
    payload = saved.json()
    record = payload["record"]
    assert record["id"]
    assert record["project_name"] == "signature_change"
    assert record["project_fingerprint"] == fingerprint
    assert record["source_filename"] == "signature_change.zip"
    assert record["change_domain"] == "function"
    assert record["change_type"] == "add_required_parameter"
    assert record["target_id"] == "utils.format_date"
    assert record["coverage_status"] == "complete"
    assert record["summary"]["direct_impact_count"] == 1
    assert payload["report"]["summary"]["indirect_2hop_count"] == 1

    assert listed.status_code == 200
    assert listed.json()["items"] == [record]

    with TestClient(app) as client:
        loaded = client.get(f"/api/v1/reports/{record['id']}")
    assert loaded.status_code == 200
    body = loaded.json()
    assert body["id"] == record["id"]
    assert body["report"]["change"]["target_symbol_id"] == "utils.format_date"
    assert body["report"]["summary"] == payload["report"]["summary"]

    with TestClient(app) as client:
        deleted = client.delete(f"/api/v1/reports/{record['id']}")
        after_delete = client.get("/api/v1/reports")
        missing_after_delete = client.get(f"/api/v1/reports/{record['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "id": record["id"]}
    assert after_delete.json()["items"] == []
    assert missing_after_delete.status_code == 404


def test_report_storage_reuses_existing_analysis_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENIMPACT_DB_PATH", str(tmp_path / "openimpact.sqlite3"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/reports",
            data={"change": json.dumps(CHANGE)},
            files={"file": ("bad.zip", b"not a zip", "application/zip")},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_zip"
    assert not (tmp_path / "openimpact.sqlite3").exists()


def test_report_history_errors_are_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENIMPACT_DB_PATH", str(tmp_path / "openimpact.sqlite3"))

    with TestClient(app) as client:
        bad_page = client.get("/api/v1/reports?limit=0")
        missing = client.get(f"/api/v1/reports/{'f' * 32}")

    assert bad_page.status_code == 422
    assert bad_page.json()["error"]["code"] == "invalid_pagination"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "report_not_found"
    with TestClient(app) as client:
        missing_delete = client.delete(f"/api/v1/reports/{'f' * 32}")
    assert missing_delete.status_code == 404
    assert missing_delete.json()["error"]["code"] == "report_not_found"
