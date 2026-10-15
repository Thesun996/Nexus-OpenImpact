"""SQLite persistence for saved projects and analysis reports.

The database stores report metadata, generated report JSON, project records,
and bounded ZIP snapshots. It does not store user credentials.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openimpact.repository.zip_inspector import MAX_UPLOAD_BYTES

SCHEMA_VERSION = 4
DEFAULT_DATABASE = Path(".openimpact") / "openimpact.sqlite3"
DEFAULT_SNAPSHOT_DIR = Path(".openimpact") / "snapshots"
REPORT_SEARCH_COLUMNS = (
    "project_name",
    "source_filename",
    "change_domain",
    "change_type",
    "target_id",
    "coverage_status",
)


class SnapshotError(ValueError):
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def database_path(path: str | Path | None = None) -> Path:
    configured = path if path is not None else os.environ.get("OPENIMPACT_DB_PATH")
    return Path(configured) if configured else DEFAULT_DATABASE


def snapshot_directory(path: str | Path | None = None) -> Path:
    configured = path if path is not None else os.environ.get("OPENIMPACT_SNAPSHOT_DIR")
    return Path(configured) if configured else DEFAULT_SNAPSHOT_DIR


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    db_path = database_path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(path: str | Path | None = None) -> None:
    with connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS analysis_reports (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                project_name TEXT NOT NULL,
                project_fingerprint TEXT NOT NULL,
                source_filename TEXT,
                analysis_root TEXT NOT NULL DEFAULT '.',
                change_domain TEXT NOT NULL DEFAULT 'function',
                change_type TEXT NOT NULL,
                target_id TEXT,
                coverage_status TEXT,
                summary_json TEXT NOT NULL,
                report_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_analysis_reports_created_at
                ON analysis_reports(created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_analysis_reports_project_fingerprint
                ON analysis_reports(project_fingerprint);

            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS project_snapshots (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                project_fingerprint TEXT NOT NULL,
                source_filename TEXT,
                analysis_root TEXT NOT NULL DEFAULT '.',
                storage_path TEXT NOT NULL,
                python_file_count INTEGER NOT NULL,
                function_count INTEGER NOT NULL,
                coverage_status TEXT,
                summary_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_project_snapshots_project_id
                ON project_snapshots(project_id, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_project_snapshots_fingerprint
                ON project_snapshots(project_fingerprint);

            CREATE INDEX IF NOT EXISTS idx_projects_updated_at
                ON projects(updated_at DESC);

            CREATE TABLE IF NOT EXISTS analysis_tasks (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                project_snapshot_id TEXT NOT NULL,
                status TEXT NOT NULL,
                change_json TEXT NOT NULL,
                expected_fingerprint TEXT,
                result_report_id TEXT,
                error_code TEXT,
                error_message TEXT,
                worker_id TEXT,
                lease_expires_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_analysis_tasks_updated_at
                ON analysis_tasks(updated_at DESC);

            CREATE INDEX IF NOT EXISTS idx_analysis_tasks_snapshot_id
                ON analysis_tasks(project_snapshot_id);
            """
        )
        _ensure_column(connection, "analysis_tasks", "worker_id", "TEXT")
        _ensure_column(connection, "analysis_tasks", "lease_expires_at", "TEXT")
        _ensure_column(connection, "analysis_tasks", "expected_fingerprint", "TEXT")
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def save_project_snapshot(
    inspect_report: dict[str, Any],
    zip_bytes: bytes,
    *,
    source_filename: str | None = None,
    analysis_root: str = ".",
    path: str | Path | None = None,
    snapshot_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Persist one uploaded project snapshot and return public metadata."""
    initialize_database(path)
    project_id = uuid.uuid4().hex
    snapshot_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    project_name = str(inspect_report.get("project_name") or "未命名项目")
    fingerprint = hashlib.sha256(zip_bytes).hexdigest()
    if fingerprint != inspect_report.get("project_fingerprint") or len(zip_bytes) > MAX_UPLOAD_BYTES:
        raise SnapshotError("snapshot_mismatch", "项目快照与读取结果不一致，请重新上传。", 409)
    coverage = inspect_report.get("coverage") if isinstance(inspect_report.get("coverage"), dict) else {}
    summary = {
        "source_root": inspect_report.get("source_root"),
        "python_file_count": _int_value(coverage.get("python_files")),
        "function_count": _int_value(coverage.get("indexed_functions")),
        "module_count": _int_value(coverage.get("indexed_modules")),
        "coverage_status": coverage.get("status") if isinstance(coverage.get("status"), str) else None,
    }

    snapshots_root = snapshot_directory(snapshot_dir)
    snapshots_root.mkdir(parents=True, exist_ok=True)
    storage_path = snapshots_root / f"{fingerprint}.zip"
    with connect(path) as connection:
        # Serialize file publication and reference changes with last-reference deletion.
        connection.execute("BEGIN IMMEDIATE")
        if storage_path.is_symlink():
            raise SnapshotError("snapshot_unavailable", "项目快照无法保存，请检查本地存储。", 503)
        # A fresh validated upload can repair a damaged file with the same digest.
        temporary_path = snapshots_root / f".{snapshot_id}.tmp"
        try:
            temporary_path.write_bytes(zip_bytes)
            temporary_path.replace(storage_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
        existing_project = None if project_name == "未命名项目" else connection.execute(
            """
            SELECT id, created_at FROM projects
            WHERE name = ?
            ORDER BY updated_at DESC, rowid DESC
            LIMIT 1
            """,
            (project_name,),
        ).fetchone()
        if existing_project is None:
            project_created_at = created_at
            connection.execute(
                """
                INSERT INTO projects (id, created_at, updated_at, name)
                VALUES (?, ?, ?, ?)
                """,
                (project_id, created_at, created_at, project_name),
            )
        else:
            project_id = existing_project["id"]
            project_created_at = existing_project["created_at"]
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (created_at, project_id),
            )
        connection.execute(
            """
            INSERT INTO project_snapshots (
                id, project_id, created_at, project_fingerprint, source_filename,
                analysis_root, storage_path, python_file_count, function_count,
                coverage_status, summary_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id, project_id, created_at, fingerprint, source_filename,
                analysis_root, storage_path.resolve().as_posix(), summary["python_file_count"],
                summary["function_count"], summary["coverage_status"],
                json.dumps(summary, ensure_ascii=False, sort_keys=True),
            ),
        )

    return {
        "project": {
            "id": project_id,
            "created_at": project_created_at,
            "updated_at": created_at,
            "name": project_name,
            "latest_snapshot": _snapshot_record({
                "id": snapshot_id,
                "project_id": project_id,
                "created_at": created_at,
                "project_fingerprint": fingerprint,
                "source_filename": source_filename,
                "analysis_root": analysis_root,
                "python_file_count": summary["python_file_count"],
                "function_count": summary["function_count"],
                "coverage_status": summary["coverage_status"],
                "summary_json": json.dumps(summary, ensure_ascii=False, sort_keys=True),
            }),
        },
        "snapshot": _snapshot_record({
            "id": snapshot_id,
            "project_id": project_id,
            "created_at": created_at,
            "project_fingerprint": fingerprint,
            "source_filename": source_filename,
            "analysis_root": analysis_root,
            "python_file_count": summary["python_file_count"],
            "function_count": summary["function_count"],
            "coverage_status": summary["coverage_status"],
            "summary_json": json.dumps(summary, ensure_ascii=False, sort_keys=True),
        }),
    }


def list_projects(
    *, limit: int = 20, offset: int = 0, query: str | None = None, path: str | Path | None = None
) -> list[dict[str, Any]]:
    initialize_database(path)
    where_sql, query_params = _project_search_clause(query)
    with connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT p.id, p.created_at, p.updated_at, p.name,
                   s.id AS snapshot_id, s.project_id AS snapshot_project_id,
                   s.created_at AS snapshot_created_at, s.project_fingerprint,
                   s.source_filename, s.analysis_root, s.python_file_count,
                   s.function_count, s.coverage_status, s.summary_json
            FROM projects p
            LEFT JOIN project_snapshots s ON s.id = (
                SELECT id FROM project_snapshots
                WHERE project_id = p.id
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
            )
            {where_sql}
            ORDER BY p.updated_at DESC, p.rowid DESC
            LIMIT ? OFFSET ?
            """,
            (*query_params, limit, offset),
        ).fetchall()
    return [_project_row_to_record(row) for row in rows]


def get_project(project_id: str, *, path: str | Path | None = None) -> dict[str, Any] | None:
    initialize_database(path)
    with connect(path) as connection:
        row = connection.execute(
            """
            SELECT p.id, p.created_at, p.updated_at, p.name,
                   s.id AS snapshot_id, s.project_id AS snapshot_project_id,
                   s.created_at AS snapshot_created_at, s.project_fingerprint,
                   s.source_filename, s.analysis_root, s.python_file_count,
                   s.function_count, s.coverage_status, s.summary_json
            FROM projects p
            LEFT JOIN project_snapshots s ON s.id = (
                SELECT id FROM project_snapshots
                WHERE project_id = p.id
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
            )
            WHERE p.id = ?
            """,
            (project_id,),
        ).fetchone()
    return _project_row_to_record(row) if row is not None else None


def list_project_snapshots(
    project_id: str, *, limit: int = 20, offset: int = 0, path: str | Path | None = None
) -> list[dict[str, Any]]:
    initialize_database(path)
    with connect(path) as connection:
        rows = connection.execute(
            """
            SELECT id, project_id, created_at, project_fingerprint, source_filename,
                   analysis_root, python_file_count, function_count, coverage_status,
                   summary_json
            FROM project_snapshots
            WHERE project_id = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT ? OFFSET ?
            """,
            (project_id, limit, offset),
        ).fetchall()
    return [_snapshot_row_to_record(row) for row in rows]


def delete_project(
    project_id: str, *, path: str | Path | None = None, snapshot_dir: str | Path | None = None
) -> bool:
    initialize_database(path)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            "SELECT project_fingerprint, storage_path FROM project_snapshots WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        cursor = connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        if cursor.rowcount <= 0:
            return False
        candidates = [(row["project_fingerprint"], row["storage_path"]) for row in rows]
        _delete_unreferenced_snapshot_files(connection, candidates, snapshot_dir=snapshot_dir)
    return True


def delete_project_snapshot(
    snapshot_id: str,
    *,
    project_id: str | None = None,
    path: str | Path | None = None,
    snapshot_dir: str | Path | None = None,
) -> dict[str, Any] | None:
    initialize_database(path)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        where = "id = ?" if project_id is None else "id = ? AND project_id = ?"
        params = (snapshot_id,) if project_id is None else (snapshot_id, project_id)
        row = connection.execute(
            f"SELECT * FROM project_snapshots WHERE {where}", params
        ).fetchone()
        if row is None:
            return None
        snapshot_project_id = row["project_id"]
        snapshot = _snapshot_row_to_record(row)
        candidate = (row["project_fingerprint"], row["storage_path"])
        connection.execute("DELETE FROM project_snapshots WHERE id = ?", (snapshot_id,))
        latest = connection.execute(
            """
            SELECT created_at FROM project_snapshots
            WHERE project_id = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
            """,
            (snapshot_project_id,),
        ).fetchone()
        if latest is None:
            connection.execute("DELETE FROM projects WHERE id = ?", (snapshot_project_id,))
            snapshot["project_deleted"] = True
        else:
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (latest["created_at"], snapshot_project_id),
            )
            snapshot["project_deleted"] = False
        _delete_unreferenced_snapshot_files(connection, [candidate], snapshot_dir=snapshot_dir)
    return snapshot


def read_project_snapshot(
    snapshot_id: str, *, path: str | Path | None = None, snapshot_dir: str | Path | None = None
) -> tuple[dict[str, Any], bytes]:
    """Read only a recorded snapshot inside the configured store; verify every use."""
    if not re.fullmatch(r"[0-9a-f]{32}", snapshot_id):
        raise SnapshotError("snapshot_not_found", "没有找到该项目快照。", 404)
    initialize_database(path)
    with connect(path) as connection:
        row = connection.execute(
            "SELECT * FROM project_snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
    if row is None:
        raise SnapshotError("snapshot_not_found", "没有找到该项目快照。", 404)
    fingerprint = row["project_fingerprint"]
    root = snapshot_directory(snapshot_dir).resolve()
    stored = Path(row["storage_path"])
    if (not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
            or stored.is_symlink() or stored.resolve() != root / f"{fingerprint}.zip"):
        raise SnapshotError("snapshot_unavailable", "项目快照存储位置不可用，请重新保存项目。", 503)
    try:
        # The byte limit and digest apply to the same open file, before any extraction.
        if stored.exists() and not stored.is_file():
            raise SnapshotError("snapshot_unavailable", "项目快照不是可读取的普通文件。", 503)
        with stored.open("rb") as stream:
            data = stream.read(MAX_UPLOAD_BYTES + 1)
    except FileNotFoundError:
        raise SnapshotError("snapshot_missing", "项目快照文件已丢失，请重新上传并保存项目。", 404) from None
    if len(data) > MAX_UPLOAD_BYTES or hashlib.sha256(data).hexdigest() != fingerprint:
        raise SnapshotError("snapshot_corrupted", "项目快照内容已改变，请重新上传并保存项目。", 409)
    return _snapshot_row_to_record(row), data


def _delete_unreferenced_snapshot_files(
    connection: sqlite3.Connection,
    candidates: list[tuple[str, str | None]],
    *,
    snapshot_dir: str | Path | None = None,
) -> None:
    root = snapshot_directory(snapshot_dir).resolve()
    for fingerprint, storage_path in candidates:
        if not re.fullmatch(r"[0-9a-f]{64}", fingerprint or "") or not storage_path:
            continue
        remaining = connection.execute(
            "SELECT 1 FROM project_snapshots WHERE project_fingerprint = ? LIMIT 1",
            (fingerprint,),
        ).fetchone()
        if remaining is not None:
            continue
        stored = Path(storage_path)
        try:
            resolved = stored.resolve()
        except OSError:
            continue
        if stored.is_symlink() or resolved != root / f"{fingerprint}.zip":
            continue
        try:
            if stored.is_file():
                stored.unlink()
        except FileNotFoundError:
            pass


def save_report(
    report: dict[str, Any],
    *,
    source_filename: str | None = None,
    analysis_root: str = ".",
    path: str | Path | None = None,
) -> dict[str, Any]:
    initialize_database(path)
    with connect(path) as connection:
        return _insert_report(connection, report, source_filename=source_filename, analysis_root=analysis_root)


def _insert_report(
    connection: sqlite3.Connection, report: dict[str, Any], *, source_filename: str | None, analysis_root: str
) -> dict[str, Any]:
    record_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    change = _change_payload(report)
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    coverage = report.get("coverage") if isinstance(report.get("coverage"), dict) else {}
    record = {
        "id": record_id,
        "created_at": created_at,
        "project_name": str(report.get("project_name") or "未命名项目"),
        "project_fingerprint": str(report.get("project_fingerprint") or ""),
        "source_filename": source_filename,
        "analysis_root": analysis_root,
        "change_domain": _change_domain(report, change),
        "change_type": str(change.get("change_type") or "unknown"),
        "target_id": _target_id(change),
        "coverage_status": coverage.get("status") if isinstance(coverage.get("status"), str) else None,
        "summary": summary,
    }
    connection.execute(
        """
        INSERT INTO analysis_reports (
            id, created_at, project_name, project_fingerprint, source_filename,
            analysis_root, change_domain, change_type, target_id, coverage_status,
            summary_json, report_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["id"], record["created_at"], record["project_name"],
            record["project_fingerprint"], record["source_filename"],
            record["analysis_root"], record["change_domain"], record["change_type"],
            record["target_id"], record["coverage_status"],
            json.dumps(summary, ensure_ascii=False, sort_keys=True),
            json.dumps(report, ensure_ascii=False, sort_keys=True),
        ),
    )
    return record


def list_reports(
    *, limit: int = 20, offset: int = 0, query: str | None = None, path: str | Path | None = None
) -> list[dict[str, Any]]:
    initialize_database(path)
    where_sql, query_params = _search_clause(query)
    with connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT id, created_at, project_name, project_fingerprint, source_filename,
                   analysis_root, change_domain, change_type, target_id, coverage_status,
                   summary_json
            FROM analysis_reports
            {where_sql}
            ORDER BY created_at DESC, rowid DESC
            LIMIT ? OFFSET ?
            """,
            (*query_params, limit, offset),
        ).fetchall()
    return [_row_to_record(row) for row in rows]


def get_report(report_id: str, *, path: str | Path | None = None) -> dict[str, Any] | None:
    initialize_database(path)
    with connect(path) as connection:
        row = connection.execute(
            """
            SELECT id, created_at, project_name, project_fingerprint, source_filename,
                   analysis_root, change_domain, change_type, target_id, coverage_status,
                   summary_json, report_json
            FROM analysis_reports
            WHERE id = ?
            """,
            (report_id,),
        ).fetchone()
    if row is None:
        return None
    record = _row_to_record(row)
    record["report"] = json.loads(row["report_json"])
    return record


def delete_report(report_id: str, *, path: str | Path | None = None) -> bool:
    initialize_database(path)
    with connect(path) as connection:
        cursor = connection.execute("DELETE FROM analysis_reports WHERE id = ?", (report_id,))
        if cursor.rowcount > 0:
            connection.execute(
                """UPDATE analysis_tasks SET status = 'failed', result_report_id = NULL,
                   error_code = 'report_deleted', error_message = ?, updated_at = ?
                   WHERE result_report_id = ? AND status = 'succeeded'""",
                ("分析报告已删除，可重新执行任务生成新报告。",
                 datetime.now(timezone.utc).isoformat(timespec="microseconds"), report_id),
            )
    return cursor.rowcount > 0


def create_analysis_task(
    *, project_snapshot_id: str, change: dict[str, Any], expected_fingerprint: str | None = None,
    path: str | Path | None = None
) -> dict[str, Any]:
    initialize_database(path)
    task_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    change_json = json.dumps(change, ensure_ascii=False, sort_keys=True)
    with connect(path) as connection:
        connection.execute(
            """
            INSERT INTO analysis_tasks (
                id, created_at, updated_at, project_snapshot_id, status, change_json, expected_fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, created_at, created_at, project_snapshot_id, "queued", change_json, expected_fingerprint),
        )
    return {
        "id": task_id,
        "created_at": created_at,
        "updated_at": created_at,
        "project_snapshot_id": project_snapshot_id,
        "status": "queued",
        "change": change,
        "result_report_id": None,
        "error_code": None,
        "error_message": None,
    }


def get_analysis_task(task_id: str, *, path: str | Path | None = None) -> dict[str, Any] | None:
    initialize_database(path)
    with connect(path) as connection:
        row = connection.execute("SELECT * FROM analysis_tasks WHERE id = ?", (task_id,)).fetchone()
    return _task_row_to_record(row) if row is not None else None


def list_analysis_tasks(
    *, limit: int = 20, offset: int = 0, path: str | Path | None = None
) -> list[dict[str, Any]]:
    initialize_database(path)
    with connect(path) as connection:
        rows = connection.execute(
            """
            SELECT * FROM analysis_tasks
            ORDER BY created_at DESC, rowid DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return [_task_row_to_record(row) for row in rows]


def claim_next_analysis_task(
    *, worker_id: str, lease_seconds: int = 300, path: str | Path | None = None
) -> dict[str, Any] | None:
    """Atomically claim one queued or expired local task for a single worker."""
    if not worker_id or lease_seconds < 1:
        raise ValueError("worker_id and a positive lease are required")
    initialize_database(path)
    now = datetime.now(timezone.utc)
    updated_at = now.isoformat(timespec="microseconds")
    expires_at = (now.timestamp() + lease_seconds)
    lease_expires_at = datetime.fromtimestamp(expires_at, timezone.utc).isoformat(timespec="microseconds")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT * FROM analysis_tasks
            WHERE status = 'queued'
               OR (status = 'running' AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?)
            ORDER BY created_at ASC, rowid ASC
            LIMIT 1
            """,
            (updated_at,),
        ).fetchone()
        if row is None:
            return None
        connection.execute(
            """
            UPDATE analysis_tasks
            SET updated_at = ?, status = 'running', worker_id = ?, lease_expires_at = ?
            WHERE id = ?
            """,
            (updated_at, worker_id, lease_expires_at, row["id"]),
        )
        claimed = connection.execute("SELECT * FROM analysis_tasks WHERE id = ?", (row["id"],)).fetchone()
    return _task_row_to_record(claimed, include_execution=True)


def finish_analysis_task(
    task_id: str,
    *,
    worker_id: str,
    status: str,
    lease_token: str | None = None,
    report: dict[str, Any] | None = None,
    source_filename: str | None = None,
    analysis_root: str = ".",
    result_report_id: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Finish only a task still leased by this worker, avoiding late overwrites."""
    if status not in {"succeeded", "failed"}:
        raise ValueError("task completion must be succeeded or failed")
    initialize_database(path)
    updated_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        owner = connection.execute(
            """SELECT id FROM analysis_tasks WHERE id = ? AND status = 'running' AND worker_id = ?
               AND (? IS NULL OR lease_expires_at = ?)""",
            (task_id, worker_id, lease_token, lease_token),
        ).fetchone()
        if owner is None:
            return None
        if report is not None:
            if status != "succeeded" or lease_token is None:
                raise ValueError("report publication requires a successful leased execution")
            record = _insert_report(connection, report, source_filename=source_filename, analysis_root=analysis_root)
            result_report_id = record["id"]
        cursor = connection.execute(
            """
            UPDATE analysis_tasks
            SET updated_at = ?, status = ?, result_report_id = ?, error_code = ?, error_message = ?,
                worker_id = NULL, lease_expires_at = NULL
            WHERE id = ? AND status = 'running' AND worker_id = ?
            """,
            (updated_at, status, result_report_id, error_code, error_message, task_id, worker_id),
        )
        if cursor.rowcount <= 0:
            return None
        row = connection.execute("SELECT * FROM analysis_tasks WHERE id = ?", (task_id,)).fetchone()
    return _task_row_to_record(row)


def update_analysis_task(
    task_id: str,
    *,
    status: str,
    result_report_id: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    path: str | Path | None = None,
) -> dict[str, Any] | None:
    if status not in {"queued", "running", "succeeded", "failed"}:
        raise ValueError("unsupported task status")
    initialize_database(path)
    updated_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    with connect(path) as connection:
        cursor = connection.execute(
            """
            UPDATE analysis_tasks
            SET updated_at = ?, status = ?, result_report_id = ?, error_code = ?, error_message = ?
            WHERE id = ?
            """,
            (updated_at, status, result_report_id, error_code, error_message, task_id),
        )
        if cursor.rowcount <= 0:
            return None
        row = connection.execute("SELECT * FROM analysis_tasks WHERE id = ?", (task_id,)).fetchone()
    return _task_row_to_record(row)


def _change_payload(report: dict[str, Any]) -> dict[str, Any]:
    change = report.get("change")
    return change if isinstance(change, dict) else {}


def _change_domain(report: dict[str, Any], change: dict[str, Any]) -> str:
    domain = report.get("change_domain") or change.get("change_domain")
    return domain if isinstance(domain, str) and domain else "function"


def _target_id(change: dict[str, Any]) -> str | None:
    for key in ("target_symbol_id", "target_module_id"):
        value = change.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _search_clause(query: str | None) -> tuple[str, tuple[str, ...]]:
    terms = [term for term in (query or "").strip().split() if term]
    if not terms:
        return "", ()
    clauses: list[str] = []
    params: list[str] = []
    for term in terms:
        pattern = f"%{_escape_like(term)}%"
        column_clauses = [f"{column} LIKE ? ESCAPE '\\'" for column in REPORT_SEARCH_COLUMNS]
        clauses.append(f"({' OR '.join(column_clauses)})")
        params.extend([pattern] * len(REPORT_SEARCH_COLUMNS))
    return f"WHERE {' AND '.join(clauses)}", tuple(params)


def _project_search_clause(query: str | None) -> tuple[str, tuple[str, ...]]:
    terms = [term for term in (query or "").strip().split() if term]
    if not terms:
        return "", ()
    columns = ("p.name", "s.source_filename", "s.project_fingerprint", "s.coverage_status")
    clauses: list[str] = []
    params: list[str] = []
    for term in terms:
        pattern = f"%{_escape_like(term)}%"
        column_clauses = [f"{column} LIKE ? ESCAPE '\\'" for column in columns]
        clauses.append(f"({' OR '.join(column_clauses)})")
        params.extend([pattern] * len(columns))
    return f"WHERE {' AND '.join(clauses)}", tuple(params)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _int_value(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _snapshot_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "created_at": row["created_at"],
        "project_fingerprint": row["project_fingerprint"],
        "source_filename": row["source_filename"],
        "analysis_root": row["analysis_root"],
        "python_file_count": row["python_file_count"],
        "function_count": row["function_count"],
        "coverage_status": row["coverage_status"],
        "summary": json.loads(row["summary_json"]),
    }


def _snapshot_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    return _snapshot_record({key: row[key] for key in row.keys()})


def _project_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    latest_snapshot = None
    if row["snapshot_id"] is not None:
        latest_snapshot = _snapshot_record({
            "id": row["snapshot_id"],
            "project_id": row["snapshot_project_id"],
            "created_at": row["snapshot_created_at"],
            "project_fingerprint": row["project_fingerprint"],
            "source_filename": row["source_filename"],
            "analysis_root": row["analysis_root"],
            "python_file_count": row["python_file_count"],
            "function_count": row["function_count"],
            "coverage_status": row["coverage_status"],
            "summary_json": row["summary_json"],
        })
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "name": row["name"],
        "latest_snapshot": latest_snapshot,
    }


def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "project_name": row["project_name"],
        "project_fingerprint": row["project_fingerprint"],
        "source_filename": row["source_filename"],
        "analysis_root": row["analysis_root"],
        "change_domain": row["change_domain"],
        "change_type": row["change_type"],
        "target_id": row["target_id"],
        "coverage_status": row["coverage_status"],
        "summary": json.loads(row["summary_json"]),
    }


def _task_row_to_record(row: sqlite3.Row, *, include_execution: bool = False) -> dict[str, Any]:
    record = {
        "id": row["id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "project_snapshot_id": row["project_snapshot_id"],
        "status": row["status"],
        "change": json.loads(row["change_json"]),
        "result_report_id": row["result_report_id"],
        "error_code": row["error_code"],
        "error_message": row["error_message"],
    }
    if include_execution:
        record["_expected_fingerprint"] = row["expected_fingerprint"]
        # A fresh claim timestamp fences even a reused worker identifier.
        record["_lease_token"] = row["lease_expires_at"]
    return record
