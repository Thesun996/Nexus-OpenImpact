"""SQLite persistence for saved projects and reports."""

from openimpact.storage import (
    delete_report,
    get_project,
    get_report,
    initialize_database,
    list_project_snapshots,
    list_projects,
    list_reports,
    save_project_snapshot,
    save_report,
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


def inspect_report(project="signature_change"):
    return {
        "project_name": project,
        "project_fingerprint": "b" * 64,
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
    assert (snapshots / f"{'b' * 64}.zip").read_bytes() == b"zip-bytes"

    assert list_projects(path=path) == [project]
    assert list_projects(path=path, query="signature complete") == [project]
    assert get_project(project["id"], path=path) == project
    assert list_project_snapshots(project["id"], path=path) == [snapshot]


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
