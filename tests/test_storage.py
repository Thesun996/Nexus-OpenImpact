"""SQLite persistence for saved projects and reports."""

import hashlib

from openimpact.storage import (
    create_analysis_task,
    delete_project,
    delete_project_snapshot,
    delete_report,
    get_analysis_task,
    get_project,
    get_report,
    initialize_database,
    list_analysis_tasks,
    list_project_snapshots,
    list_projects,
    list_reports,
    save_project_snapshot,
    save_report,
    update_analysis_task,
)


def report(project="signature_change", target="utils.format_date"):
    return {
        "project_name": project,
        "project_fingerprint": "a" * 64,
        "change": {
            "change_type": "add_required_parameter",
            "target_symbol_id": target,
        },
        "coverage": {"status": "complete"},
        "summary": {
            "direct_impact_count": 1,
            "indirect_1hop_count": 1,
            "indirect_2hop_count": 1,
            "manual_review_count": 0,
            "unresolved_call_count": 0,
        },
        "direct_impacts": [],
    }


def inspect_report(project="signature_change", zip_bytes=b"zip-bytes"):
    return {
        "project_name": project,
        "project_fingerprint": hashlib.sha256(zip_bytes).hexdigest(),
        "source_root": project,
        "coverage": {
            "status": "complete",
            "python_files": 4,
            "indexed_modules": 4,
            "indexed_functions": 4,
        },
    }


def test_initialize_database_creates_expected_tables(tmp_path):
    path = tmp_path / "openimpact.sqlite3"
    initialize_database(path)

    assert path.exists()
    assert list_reports(path=path) == []
    assert list_projects(path=path) == []


def test_save_list_and_read_project_snapshot_round_trip(tmp_path):
    path = tmp_path / "openimpact.sqlite3"
    snapshots = tmp_path / "snapshots"
    saved = save_project_snapshot(
        inspect_report(),
        b"zip-bytes",
        source_filename="signature_change.zip",
        path=path,
        snapshot_dir=snapshots,
    )

    project = saved["project"]
    snapshot = saved["snapshot"]
    assert project["id"]
    assert project["name"] == "signature_change"
    assert project["latest_snapshot"] == snapshot
    assert snapshot["project_id"] == project["id"]
    assert snapshot["source_filename"] == "signature_change.zip"
    assert snapshot["python_file_count"] == 4
    assert snapshot["function_count"] == 4
    assert snapshot["coverage_status"] == "complete"
    assert (snapshots / f"{snapshot['project_fingerprint']}.zip").read_bytes() == b"zip-bytes"

    assert list_projects(path=path) == [project]
    assert list_projects(path=path, query="signature complete") == [project]
    assert get_project(project["id"], path=path) == project
    assert list_project_snapshots(project["id"], path=path) == [snapshot]


def test_save_project_snapshot_appends_versions_for_same_named_project(tmp_path):
    path = tmp_path / "openimpact.sqlite3"
    snapshots = tmp_path / "snapshots"
    first = save_project_snapshot(
        inspect_report("signature_change", b"first-zip"),
        b"first-zip",
        source_filename="signature_change-v1.zip",
        path=path,
        snapshot_dir=snapshots,
    )
    second = save_project_snapshot(
        inspect_report("signature_change", b"second-zip"),
        b"second-zip",
        source_filename="signature_change-v2.zip",
        path=path,
        snapshot_dir=snapshots,
    )

    assert second["project"]["id"] == first["project"]["id"]
    assert second["project"]["created_at"] == first["project"]["created_at"]
    assert second["project"]["updated_at"] != first["project"]["updated_at"]
    assert second["project"]["latest_snapshot"] == second["snapshot"]
    assert list_projects(path=path) == [second["project"]]
    assert list_project_snapshots(first["project"]["id"], path=path) == [second["snapshot"], first["snapshot"]]
    assert (snapshots / f"{first['snapshot']['project_fingerprint']}.zip").read_bytes() == b"first-zip"
    assert (snapshots / f"{second['snapshot']['project_fingerprint']}.zip").read_bytes() == b"second-zip"


def test_unnamed_project_snapshots_do_not_merge(tmp_path):
    path = tmp_path / "openimpact.sqlite3"
    first = save_project_snapshot(inspect_report("", b"first"), b"first", path=path, snapshot_dir=tmp_path / "snapshots")
    second = save_project_snapshot(inspect_report("", b"second"), b"second", path=path, snapshot_dir=tmp_path / "snapshots")

    assert first["project"]["id"] != second["project"]["id"]
    assert len(list_projects(path=path)) == 2


def test_save_list_and_read_report_round_trip(tmp_path):
    path = tmp_path / "openimpact.sqlite3"
    saved = save_report(report(), source_filename="signature_change.zip", analysis_root=".", path=path)

    assert saved["id"]
    assert saved["project_name"] == "signature_change"
    assert saved["change_domain"] == "function"
    assert saved["change_type"] == "add_required_parameter"
    assert saved["target_id"] == "utils.format_date"
    assert saved["coverage_status"] == "complete"
    assert saved["summary"]["direct_impact_count"] == 1

    items = list_reports(path=path)
    assert len(items) == 1
    assert items[0] == saved

    loaded = get_report(saved["id"], path=path)
    assert loaded["id"] == saved["id"]
    assert loaded["report"]["change"]["target_symbol_id"] == "utils.format_date"
    assert loaded["report"]["summary"] == saved["summary"]


def test_list_reports_uses_newest_first_and_limit_offset(tmp_path):
    path = tmp_path / "openimpact.sqlite3"
    first = save_report(report("first"), path=path)
    second = save_report(report("second"), path=path)

    assert [item["id"] for item in list_reports(path=path, limit=1)] == [second["id"]]
    assert [item["id"] for item in list_reports(path=path, limit=1, offset=1)] == [first["id"]]


def test_list_reports_filters_saved_metadata(tmp_path):
    path = tmp_path / "openimpact.sqlite3"
    target = save_report(report("signature_change"), source_filename="signature_change.zip", path=path)
    save_report(report("other_project", target="other.render"), source_filename="other.zip", path=path)

    assert [item["id"] for item in list_reports(path=path, query="format_date")] == [target["id"]]
    assert [item["id"] for item in list_reports(path=path, query="signature zip")] == [target["id"]]
    assert list_reports(path=path, query="missing") == []


def test_missing_report_returns_none(tmp_path):
    path = tmp_path / "openimpact.sqlite3"
    initialize_database(path)

    assert get_report("f" * 32, path=path) is None


def test_delete_report_removes_only_existing_record(tmp_path):
    path = tmp_path / "openimpact.sqlite3"
    saved = save_report(report(), path=path)

    assert delete_report(saved["id"], path=path) is True
    assert get_report(saved["id"], path=path) is None
    assert list_reports(path=path) == []
    assert delete_report(saved["id"], path=path) is False


def test_analysis_task_round_trip_and_status_updates(tmp_path):
    path = tmp_path / "openimpact.sqlite3"
    change = {"target_symbol_id": "utils.format_date", "added_parameter": {"name": "timezone"}}
    task = create_analysis_task(project_snapshot_id="a" * 32, change=change, path=path)

    assert task["id"]
    assert task["status"] == "queued"
    assert task["change"] == change
    assert get_analysis_task(task["id"], path=path) == task
    assert list_analysis_tasks(path=path) == [task]

    running = update_analysis_task(task["id"], status="running", path=path)
    assert running["status"] == "running"
    succeeded = update_analysis_task(task["id"], status="succeeded", result_report_id="b" * 32, path=path)
    assert succeeded["result_report_id"] == "b" * 32
    failed = update_analysis_task(task["id"], status="failed", error_code="analysis_failed", error_message="失败", path=path)
    assert failed["status"] == "failed"
    assert failed["error_code"] == "analysis_failed"
    assert update_analysis_task("f" * 32, status="running", path=path) is None


def test_task_pagination_does_not_move_rows_when_status_changes(tmp_path):
    path = tmp_path / "tasks.sqlite3"
    old = create_analysis_task(project_snapshot_id="a" * 32, change={}, path=path)
    new = create_analysis_task(project_snapshot_id="a" * 32, change={}, path=path)
    assert list_analysis_tasks(limit=1, path=path)[0]["id"] == new["id"]
    update_analysis_task(old["id"], status="running", path=path)
    assert list_analysis_tasks(limit=1, offset=1, path=path)[0]["id"] == old["id"]


def test_delete_project_removes_records_and_only_unreferenced_snapshot_file(tmp_path):
    path = tmp_path / "openimpact.sqlite3"
    snapshots = tmp_path / "snapshots"
    first = save_project_snapshot(inspect_report("first"), b"zip-bytes", path=path, snapshot_dir=snapshots)
    second = save_project_snapshot(inspect_report("second"), b"zip-bytes", path=path, snapshot_dir=snapshots)
    snapshot_file = snapshots / f"{first['snapshot']['project_fingerprint']}.zip"

    assert snapshot_file.exists()
    assert delete_project(first["project"]["id"], path=path, snapshot_dir=snapshots) is True
    assert get_project(first["project"]["id"], path=path) is None
    assert list_project_snapshots(first["project"]["id"], path=path) == []
    assert snapshot_file.exists()

    assert delete_project(second["project"]["id"], path=path, snapshot_dir=snapshots) is True
    assert not snapshot_file.exists()
    assert delete_project(second["project"]["id"], path=path, snapshot_dir=snapshots) is False


def test_delete_project_snapshot_checks_project_and_removes_empty_project(tmp_path):
    path = tmp_path / "openimpact.sqlite3"
    snapshots = tmp_path / "snapshots"
    saved = save_project_snapshot(inspect_report(), b"zip-bytes", path=path, snapshot_dir=snapshots)
    project = saved["project"]
    snapshot = saved["snapshot"]
    snapshot_file = snapshots / f"{snapshot['project_fingerprint']}.zip"

    assert delete_project_snapshot(snapshot["id"], project_id="f" * 32, path=path, snapshot_dir=snapshots) is None
    assert get_project(project["id"], path=path) == project
    deleted = delete_project_snapshot(snapshot["id"], project_id=project["id"], path=path, snapshot_dir=snapshots)

    assert deleted["id"] == snapshot["id"]
    assert deleted["project_deleted"] is True
    assert get_project(project["id"], path=path) is None
    assert not snapshot_file.exists()
