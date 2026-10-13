"""SQLite persistence for saved projects and analysis reports.

The database stores report metadata, generated report JSON, project records,
and bounded ZIP snapshots. It does not store user credentials.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
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
            """
        )
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


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
    fingerprint = str(inspect_report.get("project_fingerprint") or "")
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
    if not storage_path.exists():
        temporary_path = snapshots_root / f".{snapshot_id}.tmp"
        try:
            temporary_path.write_bytes(zip_bytes)
            temporary_path.replace(storage_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    with connect(path) as connection:
        connection.execute(
            """
            INSERT INTO projects (id, created_at, updated_at, name)
            VALUES (?, ?, ?, ?)
            """,
            (project_id, created_at, created_at, project_name),
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
                analysis_root, storage_path.as_posix(), summary["python_file_count"],
                summary["function_count"], summary["coverage_status"],
                json.dumps(summary, ensure_ascii=False, sort_keys=True),
            ),
        )

    return {
        "project": {
            "id": project_id,
            "created_at": created_at,
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


def save_report(
    report: dict[str, Any],
    *,
    source_filename: str | None = None,
    analysis_root: str = ".",
    path: str | Path | None = None,
) -> dict[str, Any]:
    initialize_database(path)
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
    with connect(path) as connection:
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
    return cursor.rowcount > 0


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
