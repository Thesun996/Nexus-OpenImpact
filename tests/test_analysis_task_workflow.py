"""Task execution preserves snapshot evidence and explicit failures."""

import json
import sqlite3
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time

import pytest

from openimpact import api
from openimpact.storage import create_analysis_task, get_analysis_task, claim_next_analysis_task
from openimpact.worker import run_once
from test_backend_stability import live_backend, make_zip, CHANGE
from test_report_storage_api import demo_zip
from fastapi.testclient import TestClient


@pytest.fixture
def task_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENIMPACT_DB_PATH", str(tmp_path / "task.sqlite3"))
    monkeypatch.setenv("OPENIMPACT_SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    monkeypatch.setenv("OPENIMPACT_LLM_PROVIDER", "rule")
    with TestClient(api.app) as client:
        yield client


def save_snapshot(client, data, root="."):
    response = client.post("/api/v1/projects", data={"analysis_root": root},
                           files={"file": ("sample.zip", data, "application/zip")})
    assert response.status_code == 200
    return response.json()["snapshot"]


def submit_task(client, snapshot, change=CHANGE):
    response = client.post("/api/v1/analysis-tasks", data={
        "project_snapshot_id": snapshot["id"], "expected_fingerprint": snapshot["project_fingerprint"],
        "change": json.dumps(change),
    })
    assert response.status_code == 202
    return response.json()["task"]


def test_invalid_signature_task_keeps_actionable_diagnostic(task_client):
    snapshot = save_snapshot(task_client, demo_zip())
    change = {**CHANGE, "added_parameter": {"name": "/", "kind": "positional_or_keyword"}}
    task = submit_task(task_client, snapshot, change)
    assert run_once(worker_id="test-invalid-signature") is True
    failed = task_client.get(f"/api/v1/analysis-tasks/{task['id']}").json()
    assert failed["status"] == "failed"
    assert failed["error_code"] == "invalid_after_signature"
    assert failed["error_message"]
    assert not failed["result_report_id"]
    assert task_client.get("/api/v1/reports").json()["items"] == []


def test_deleted_snapshot_between_submit_and_execution_has_specific_error(task_client):
    snapshot = save_snapshot(task_client, demo_zip())
    task = create_analysis_task(project_snapshot_id=snapshot["id"], change=CHANGE)
    assert task_client.delete(f"/api/v1/projects/{snapshot['project_id']}").status_code == 200
    assert run_once(worker_id="test-missing-snapshot") is True
    failed = get_analysis_task(task["id"])
    assert failed["status"] == "failed"
    assert failed["error_code"] == "snapshot_not_found"
    assert failed["result_report_id"] is None


def test_task_preserves_source_root_and_matches_synchronous_evidence(task_client):
    data = make_zip({
        "demo/src/pkg/__init__.py": b"",
        "demo/src/pkg/utils.py": b"def f(x):\n    return x\n",
        "demo/src/pkg/caller.py": b"from .utils import f\ndef caller():\n    return f(1)\n",
    })
    snapshot = save_snapshot(task_client, data, "src")
    change = {**CHANGE, "target_symbol_id": "pkg.utils.f"}
    sync = task_client.post(f"/api/v1/snapshots/{snapshot['id']}/analyze", data={
        "change": json.dumps(change), "expected_fingerprint": snapshot["project_fingerprint"],
    }).json()
    task = submit_task(task_client, snapshot, change)
    assert run_once(worker_id="test-source-root") is True
    finished = get_analysis_task(task["id"])
    assert finished["status"] == "succeeded"
    record = task_client.get(f"/api/v1/reports/{finished['result_report_id']}").json()
    assert record["analysis_root"] == record["report"]["analysis_layout"]["analysis_root"] == "src"
    for key in ("change", "summary", "evidences", "explanations", "project_snapshot_id", "project_id"):
        assert record["report"][key] == sync[key]


def test_real_task_returns_202_before_analysis_and_health_remains_available(live_backend, tmp_path, monkeypatch):
    client, _, _ = live_backend
    monkeypatch.setenv("OPENIMPACT_DB_PATH", str(tmp_path / "task.sqlite3"))
    monkeypatch.setenv("OPENIMPACT_SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    snapshot = save_snapshot(client, demo_zip())
    entered, release = Event(), Event()
    original = api._analyze_zip

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(api, "_analyze_zip", blocked)
    try:
        task = submit_task(client, snapshot)
        assert task["status"] == "queued"
        with ThreadPoolExecutor(max_workers=1) as executor:
            worker = executor.submit(run_once, worker_id="test-live-worker")
            assert entered.wait(2)
            assert client.get(f"/api/v1/analysis-tasks/{task['id']}").json()["status"] == "running"
            assert client.get("/api/v1/health").json()["status"] == "ok"
            release.set()
            assert worker.result(timeout=5) is True
    finally:
        release.set()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        finished = client.get(f"/api/v1/analysis-tasks/{task['id']}").json()
        if finished["status"] in {"failed", "succeeded"}:
            break
        time.sleep(0.01)
    assert finished["status"] == "succeeded"
    assert client.get(f"/api/v1/reports/{finished['result_report_id']}").status_code == 200


@pytest.mark.parametrize("replacement_worker", ["replacement", "original"])
def test_reclaimed_task_publishes_only_the_current_execution_report(task_client, monkeypatch, replacement_worker):
    snapshot = save_snapshot(task_client, demo_zip())
    task = submit_task(task_client, snapshot)
    old_claim = claim_next_analysis_task(worker_id="original")
    original_analyze = api._analyze_zip

    def slow_execution(*args, **kwargs):
        result = original_analyze(*args, **kwargs)
        with sqlite3.connect(os.environ["OPENIMPACT_DB_PATH"]) as db:
            db.execute("UPDATE analysis_tasks SET lease_expires_at = '2000-01-01' WHERE id = ?", (task["id"],))
        replacement = claim_next_analysis_task(worker_id=replacement_worker)
        assert replacement is not None
        with monkeypatch.context() as context:
            context.setattr(api, "_analyze_zip", original_analyze)
            api._run_claimed_analysis_task(replacement, replacement_worker)
        return result

    monkeypatch.setattr(api, "_analyze_zip", slow_execution)
    api._run_claimed_analysis_task(old_claim, "original")
    finished = get_analysis_task(task["id"])
    reports = task_client.get("/api/v1/reports").json()["items"]
    assert finished["status"] == "succeeded"
    assert [row["id"] for row in reports] == [finished["result_report_id"]]


def test_report_publication_rolls_back_if_task_completion_fails(task_client):
    snapshot = save_snapshot(task_client, demo_zip())
    task = submit_task(task_client, snapshot)
    with sqlite3.connect(os.environ["OPENIMPACT_DB_PATH"]) as db:
        db.execute("""CREATE TRIGGER fail_completion BEFORE UPDATE ON analysis_tasks
                      WHEN NEW.status = 'succeeded' BEGIN SELECT RAISE(ABORT, 'completion failed'); END""")
    assert run_once(worker_id="rollback")
    assert get_analysis_task(task["id"])["status"] == "failed"
    assert task_client.get("/api/v1/reports").json()["items"] == []


def test_deleted_task_report_marks_result_unavailable_and_can_be_retried(task_client):
    snapshot = save_snapshot(task_client, demo_zip())
    task = submit_task(task_client, snapshot)
    assert run_once(worker_id="before-delete")
    report_id = get_analysis_task(task["id"])["result_report_id"]
    assert task_client.delete(f"/api/v1/reports/{report_id}").status_code == 200
    after = get_analysis_task(task["id"])
    assert after["status"] == "failed"
    assert after["error_code"] == "report_deleted"
    assert after["result_report_id"] is None
    assert task_client.get(f"/api/v1/reports/{report_id}").status_code == 404
    retried = task_client.post(f"/api/v1/analysis-tasks/{task['id']}/retry")
    assert retried.status_code == 202
    assert retried.json()["task"]["id"] != task["id"]
    assert run_once(worker_id="after-delete")
    assert get_analysis_task(retried.json()["task"]["id"])["status"] == "succeeded"
