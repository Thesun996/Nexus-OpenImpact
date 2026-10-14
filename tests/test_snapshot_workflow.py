"""Stored snapshots must produce the same evidence as the uploaded ZIP."""

import hashlib
import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openimpact.api import app
from openimpact.storage import read_project_snapshot, SnapshotError

SAMPLE = Path(__file__).resolve().parents[1] / "frontend/public/samples/signature_change.zip"
CHANGE = {"target_symbol_id": "utils.format_date",
          "added_parameter": {"name": "timezone", "kind": "positional_or_keyword"}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENIMPACT_DB_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("OPENIMPACT_SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    with TestClient(app) as client:
        yield client


def save(client, data=None, root="."):
    response = client.post("/api/v1/projects", data={"analysis_root": root},
                           files={"file": ("sample.zip", data or SAMPLE.read_bytes(), "application/zip")})
    assert response.status_code == 200, response.text
    return response.json()


def post(client, snapshot, operation, **fields):
    return client.post(f"/api/v1/snapshots/{snapshot['id']}/{operation}",
                       data={"expected_fingerprint": snapshot["project_fingerprint"], **fields})


def test_saved_snapshot_full_workflow_without_file(client):
    created = save(client)
    snapshot = created["snapshot"]
    inspected = post(client, snapshot, "inspect")
    assert inspected.status_code == 200
    assert inspected.json()["symbols"] == created["inspect"]["symbols"]
    assert inspected.json()["snapshot"] == snapshot
    assert "storage_path" not in inspected.text
    validated = post(client, snapshot, "validate", change=json.dumps(CHANGE))
    assert validated.status_code == 200
    assert validated.json()["validation"]["valid"] is True
    analyzed = post(client, snapshot, "analyze", change=json.dumps(CHANGE))
    direct = client.post("/api/v1/projects/analyze", data={"change": json.dumps(CHANGE)},
                         files={"file": ("sample.zip", SAMPLE.read_bytes(), "application/zip")})
    assert analyzed.status_code == direct.status_code == 200
    for key in ("change", "summary", "direct_impacts", "indirect_impacts", "evidences", "explanations"):
        assert analyzed.json()[key] == direct.json()[key]
    assert analyzed.json()["project_snapshot_id"] == snapshot["id"]
    assert analyzed.json()["project_id"] == snapshot["project_id"]
    assert analyzed.json()["summary"]["direct_impact_count"] == 1
    source = post(client, snapshot, "source", path="report.py")
    assert source.status_code == 200
    assert "return format_date(date)" in source.json()["file"]["content"]
    for operation, fields in [("questions", {"question": "为什么受影响？"}), ("question-suggestions", {})]:
        response = post(client, snapshot, operation, change=json.dumps(CHANGE), **fields)
        assert response.status_code == 200, response.text
        assert response.json()["project_fingerprint"] == snapshot["project_fingerprint"]
    saved = post(client, snapshot, "reports", change=json.dumps(CHANGE))
    assert saved.status_code == 200
    loaded = client.get(f"/api/v1/reports/{saved.json()['record']['id']}")
    assert loaded.json()["report"]["project_snapshot_id"] == snapshot["id"]
    assert loaded.json()["report"]["evidences"] == analyzed.json()["evidences"]


def test_snapshot_remains_readable_after_new_client_and_original_file_gone(client):
    snapshot = save(client)["snapshot"]
    with TestClient(app) as reopened:
        assert post(reopened, snapshot, "inspect").status_code == 200


@pytest.mark.parametrize("operation", ["inspect", "validate", "analyze", "reports", "source", "questions", "question-suggestions"])
def test_snapshot_checks_stored_bytes_before_every_operation(client, tmp_path, operation):
    snapshot = save(client)["snapshot"]
    stored = tmp_path / "snapshots" / f"{snapshot['project_fingerprint']}.zip"
    stored.write_bytes(b"tampered snapshot")
    fields = {"change": json.dumps(CHANGE)} if operation in {"validate", "analyze", "reports", "questions", "question-suggestions"} else {}
    if operation == "questions":
        fields["question"] = "why"
    response = post(client, snapshot, operation, **fields)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "snapshot_corrupted"
    assert client.get("/api/v1/reports").json()["items"] == []


def test_snapshot_missing_path_tampering_and_symlink_are_safe(client, tmp_path):
    snapshot = save(client)["snapshot"]
    stored = tmp_path / "snapshots" / f"{snapshot['project_fingerprint']}.zip"
    stored.unlink()
    missing = post(client, snapshot, "inspect")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "snapshot_missing"
    outside = tmp_path / "private.zip"
    outside.write_bytes(SAMPLE.read_bytes())
    stored.symlink_to(outside)
    assert post(client, snapshot, "inspect").status_code == 503
    stored.unlink()
    with sqlite3.connect(tmp_path / "db.sqlite3") as connection:
        connection.execute("UPDATE project_snapshots SET storage_path = ?", (str(outside),))
    response = post(client, snapshot, "inspect")
    assert response.status_code == 503
    assert str(tmp_path) not in response.text


def test_snapshot_input_errors_and_invalid_changes_never_save_report(client):
    snapshot = save(client)["snapshot"]
    invalid = post(client, snapshot, "validate", change=json.dumps({**CHANGE, "target_symbol_id": "missing.f"}))
    assert invalid.status_code == 422
    assert invalid.json()["validation"]["valid"] is False
    assert post(client, snapshot, "analyze", change="{").status_code == 422
    for fields in ({"analysis_root": "other"}, {"storage_path": "/tmp/a.zip"}):
        assert post(client, snapshot, "inspect", **fields).status_code == 400
    assert post(client, snapshot, "inspect", expected_fingerprint="f" * 64).status_code == 409
    assert client.post(f"/api/v1/snapshots/{snapshot['id']}/analyze", data={"change": "{}"}).status_code == 422
    assert post(client, {**snapshot, "id": "f" * 32}, "inspect").status_code == 404
    assert post(client, snapshot, "unknown").status_code == 404
    assert post(client, snapshot, "inspect", unused="x" * 65536).status_code == 413
    duplicate = client.post(f"/api/v1/snapshots/{snapshot['id']}/inspect",
                            content="expected_fingerprint=a&expected_fingerprint=b",
                            headers={"content-type": "application/x-www-form-urlencoded"})
    assert duplicate.status_code == 400
    assert client.get("/api/v1/reports").json()["items"] == []


def test_saved_src_root_is_reused_for_validation_and_analysis(client):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("demo/src/pkg/__init__.py", "")
        archive.writestr("demo/src/pkg/utils.py", "def f(x):\n    return x\n")
        archive.writestr("demo/src/pkg/caller.py", "from .utils import f\ndef caller():\n    return f(1)\n")
    created = save(client, buffer.getvalue(), "src")
    snapshot = created["snapshot"]
    change = {**CHANGE, "target_symbol_id": "pkg.utils.f"}
    for operation in ("inspect", "validate", "analyze", "reports"):
        response = post(client, snapshot, operation, **({} if operation == "inspect" else {"change": json.dumps(change)}))
        assert response.status_code == 200, response.text
        payload = response.json()["report"] if operation == "reports" else response.json()
        assert payload["analysis_layout"]["analysis_root"] == "src"
        assert payload["project_fingerprint"] == hashlib.sha256(buffer.getvalue()).hexdigest()


def test_snapshot_reader_bounds_size(client, tmp_path):
    from openimpact.repository.zip_inspector import MAX_UPLOAD_BYTES
    snapshot = save(client)["snapshot"]
    stored = tmp_path / "snapshots" / f"{snapshot['project_fingerprint']}.zip"
    with stored.open("wb") as stream:
        stream.truncate(MAX_UPLOAD_BYTES + 1)
    with pytest.raises(SnapshotError, match="快照内容已改变"):
        read_project_snapshot(snapshot["id"])


def test_new_upload_repairs_a_corrupted_snapshot_file(client, tmp_path):
    snapshot = save(client)["snapshot"]
    stored = tmp_path / "snapshots" / f"{snapshot['project_fingerprint']}.zip"
    stored.write_bytes(b"damaged")
    repaired = save(client)["snapshot"]
    assert repaired["id"] != snapshot["id"]
    assert post(client, repaired, "inspect").status_code == 200
    assert post(client, snapshot, "inspect").status_code == 200


@pytest.mark.parametrize("domain,change_type", [
    ("module", "rename_module"), ("module", "remove_module"),
    ("symbol", "rename_module_symbol"), ("symbol", "remove_module_symbol"),
])
def test_existing_module_and_symbol_workflows_reuse_snapshot(client, domain, change_type):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("config.py", "MAX_RETRIES = 3\n")
        archive.writestr("client.py", "import config\nlimit = config.MAX_RETRIES\n")
    snapshot = save(client, buffer.getvalue())["snapshot"]
    change = {"change_domain": domain, "change_type": change_type}
    change["target_module_id" if domain == "module" else "target_symbol_id"] = "config" if domain == "module" else "config.MAX_RETRIES"
    if change_type.startswith("rename"):
        change["new_module_name" if domain == "module" else "new_symbol_name"] = "settings" if domain == "module" else "RETRY_LIMIT"
    validated = post(client, snapshot, "validate", change=json.dumps(change))
    assert validated.status_code == 200, validated.text
    saved = post(client, snapshot, "reports", change=json.dumps(change))
    assert saved.status_code == 200, saved.text
    assert saved.json()["report"]["change_domain"] == domain
    assert saved.json()["report"]["change"] == validated.json()["change_spec"]
    assert saved.json()["report"]["project_snapshot_id"] == snapshot["id"]
    assert saved.json()["report"]["evidences"]


def test_snapshot_database_failures_are_safe(client, monkeypatch):
    snapshot = save(client)["snapshot"]
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("private database path /private/secret.db")
    monkeypatch.setattr("openimpact.snapshot_api.read_project_snapshot", fail)
    result = post(client, snapshot, "inspect")
    assert result.status_code == 503
    assert "private" not in result.text
