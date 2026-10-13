"""SQLite persistence for saved analysis reports.

The database stores report metadata and the generated report JSON. It does not
store uploaded ZIP bytes or user credentials.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_DATABASE = Path(".openimpact") / "openimpact.sqlite3"


def database_path(path: str | Path | None = None) -> Path:
    configured = path if path is not None else os.environ.get("OPENIMPACT_DB_PATH")
    return Path(configured) if configured else DEFAULT_DATABASE


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
            """
        )
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


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


def list_reports(*, limit: int = 20, offset: int = 0, path: str | Path | None = None) -> list[dict[str, Any]]:
    initialize_database(path)
    with connect(path) as connection:
        rows = connection.execute(
            """
            SELECT id, created_at, project_name, project_fingerprint, source_filename,
                   analysis_root, change_domain, change_type, target_id, coverage_status,
                   summary_json
            FROM analysis_reports
            ORDER BY created_at DESC, rowid DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
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
