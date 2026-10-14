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
        filtered = client.get("/api/v1/reports?q=format_date")

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
    assert listed.json()["has_more"] is False
    assert filtered.status_code == 200
    assert filtered.json()["query"] == "format_date"
    assert filtered.json()["items"] == [record]

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


def test_create_project_snapshot_then_list_and_read(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENIMPACT_DB_PATH", str(tmp_path / "openimpact.sqlite3"))
    monkeypatch.setenv("OPENIMPACT_SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    data = demo_zip()
    fingerprint = hashlib.sha256(data).hexdigest()

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/projects",
            files={"file": ("signature_change.zip", data, "application/zip")},
        )
        listed = client.get("/api/v1/projects?q=signature")

    assert created.status_code == 200
    body = created.json()
    project = body["project"]
    snapshot = body["snapshot"]
    assert project["id"]
    assert project["name"] == "signature_change"
    assert project["latest_snapshot"] == snapshot
    assert snapshot["project_id"] == project["id"]
    assert snapshot["project_fingerprint"] == fingerprint
    assert snapshot["source_filename"] == "signature_change.zip"
    assert snapshot["python_file_count"] == 4
    assert snapshot["function_count"] == 4
    assert snapshot["coverage_status"] == "complete"
    assert body["inspect"]["project_fingerprint"] == fingerprint
    assert (tmp_path / "snapshots" / f"{fingerprint}.zip").read_bytes() == data

    assert listed.status_code == 200
    assert listed.json()["items"] == [project]
    assert listed.json()["has_more"] is False

    with TestClient(app) as client:
        loaded = client.get(f"/api/v1/projects/{project['id']}")
        snapshots = client.get(f"/api/v1/projects/{project['id']}/snapshots")
    assert loaded.status_code == 200
    assert loaded.json() == project
    assert snapshots.status_code == 200
    assert snapshots.json()["items"] == [snapshot]


def test_create_project_snapshot_appends_same_project_versions(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENIMPACT_DB_PATH", str(tmp_path / "openimpact.sqlite3"))
    monkeypatch.setenv("OPENIMPACT_SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    data = demo_zip()

    with TestClient(app) as client:
        first = client.post(
            "/api/v1/projects",
            files={"file": ("signature_change-v1.zip", data, "application/zip")},
        ).json()
        second = client.post(
            "/api/v1/projects",
            files={"file": ("signature_change-v2.zip", data, "application/zip")},
        ).json()
        listed = client.get("/api/v1/projects")
        snapshots = client.get(f"/api/v1/projects/{first['project']['id']}/snapshots")

    assert second["project"]["id"] == first["project"]["id"]
    assert second["project"]["latest_snapshot"] == second["snapshot"]
    assert listed.status_code == 200
    assert listed.json()["items"] == [second["project"]]
    assert snapshots.status_code == 200
    assert [item["id"] for item in snapshots.json()["items"]] == [second["snapshot"]["id"], first["snapshot"]["id"]]


def test_delete_project_and_snapshot_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENIMPACT_DB_PATH", str(tmp_path / "openimpact.sqlite3"))
    monkeypatch.setenv("OPENIMPACT_SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    data = demo_zip()
    fingerprint = hashlib.sha256(data).hexdigest()

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/projects",
            files={"file": ("signature_change.zip", data, "application/zip")},
        ).json()
        project = created["project"]
        snapshot = created["snapshot"]

        missing_snapshot = client.delete(f"/api/v1/projects/{project['id']}/snapshots/{'f' * 32}")
        deleted_snapshot = client.delete(f"/api/v1/projects/{project['id']}/snapshots/{snapshot['id']}")
        missing_project_after_snapshot = client.get(f"/api/v1/projects/{project['id']}")

        recreated = client.post(
            "/api/v1/projects",
            files={"file": ("signature_change.zip", data, "application/zip")},
        ).json()
        deleted_project = client.delete(f"/api/v1/projects/{recreated['project']['id']}")
        missing_project_after_delete = client.get(f"/api/v1/projects/{recreated['project']['id']}")

    assert missing_snapshot.status_code == 404
    assert missing_snapshot.json()["error"]["code"] == "snapshot_not_found"
    assert deleted_snapshot.status_code == 200
    assert deleted_snapshot.json() == {
        "deleted": True,
        "id": snapshot["id"],
        "project_id": project["id"],
        "project_deleted": True,
    }
    assert missing_project_after_snapshot.status_code == 404
    assert deleted_project.status_code == 200
    assert deleted_project.json() == {"deleted": True, "id": recreated["project"]["id"]}
    assert missing_project_after_delete.status_code == 404
    assert not (tmp_path / "snapshots" / f"{fingerprint}.zip").exists()


def test_project_storage_errors_are_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENIMPACT_DB_PATH", str(tmp_path / "openimpact.sqlite3"))
    monkeypatch.setenv("OPENIMPACT_SNAPSHOT_DIR", str(tmp_path / "snapshots"))

    with TestClient(app) as client:
        bad_zip = client.post(
            "/api/v1/projects",
            files={"file": ("bad.zip", b"not a zip", "application/zip")},
        )
        bad_page = client.get("/api/v1/projects?limit=0")
        bad_query = client.get(f"/api/v1/projects?q={'x' * 81}")
        missing = client.get(f"/api/v1/projects/{'f' * 32}")

    assert bad_zip.status_code == 400
    assert bad_zip.json()["error"]["code"] == "invalid_zip"
    assert bad_page.status_code == 422
    assert bad_page.json()["error"]["code"] == "invalid_pagination"
    assert bad_query.status_code == 422
    assert bad_query.json()["error"]["code"] == "invalid_query"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "project_not_found"


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
        bad_query = client.get(f"/api/v1/reports?q={'x' * 81}")
        missing = client.get(f"/api/v1/reports/{'f' * 32}")

    assert bad_page.status_code == 422
    assert bad_page.json()["error"]["code"] == "invalid_pagination"
    assert bad_query.status_code == 422
    assert bad_query.json()["error"]["code"] == "invalid_query"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "report_not_found"
    with TestClient(app) as client:
        missing_delete = client.delete(f"/api/v1/reports/{'f' * 32}")
    assert missing_delete.status_code == 404
    assert missing_delete.json()["error"]["code"] == "report_not_found"


def test_report_history_has_more_uses_one_extra_record(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENIMPACT_DB_PATH", str(tmp_path / "openimpact.sqlite3"))
    data = demo_zip()
    fingerprint = hashlib.sha256(data).hexdigest()
    fields = {"change": json.dumps(CHANGE), "expected_fingerprint": fingerprint}

    with TestClient(app) as client:
        first = client.post(
            "/api/v1/reports",
            data=fields,
            files={"file": ("signature_change.zip", data, "application/zip")},
        ).json()["record"]
        second = client.post(
            "/api/v1/reports",
            data=fields,
            files={"file": ("signature_change.zip", data, "application/zip")},
        ).json()["record"]
        first_page = client.get("/api/v1/reports?limit=1")
        second_page = client.get("/api/v1/reports?limit=1&offset=1")

    assert first_page.status_code == 200
    assert first_page.json()["items"] == [second]
    assert first_page.json()["has_more"] is True
    assert second_page.status_code == 200
    assert second_page.json()["items"] == [first]
    assert second_page.json()["has_more"] is False
