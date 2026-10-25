"""Reuse saved ZIP snapshots through the existing static-analysis operations."""

import json
import re
import sqlite3

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from openimpact.repository.layout import AnalysisRootError
from openimpact.repository.zip_inspector import ZipInspectionError
from openimpact.storage import SnapshotError, read_project_snapshot, save_report

router = APIRouter()

# These fields mirror the uploaded-ZIP contracts. Root and filename belong to
# the stored snapshot and cannot be overridden by request data.
_FIELDS = {
    "inspect": (set(), set()),
    "graph": (set(), set()),
    "validate": ({"change"}, set()),
    "analyze": ({"change"}, set()),
    "reports": ({"change"}, set()),
    "source": (set(), {"path"}),
    "questions": ({"change", "question"}, {"finding_index", "history"}),
    "question-suggestions": ({"change"}, {"finding_index"}),
}


def _run_snapshot(snapshot_id, operation, fields):
    from openimpact.api import _error, _inspect_zip, _graph_zip, _validate_zip, _analyze_zip, _fingerprint_error
    from openimpact.workspace_api import _source, _question, _suggestions

    snapshot, data = read_project_snapshot(snapshot_id)
    expected = fields.get("expected_fingerprint")
    if error := _fingerprint_error(data, expected):
        return error
    filename = snapshot["source_filename"]
    root = snapshot["analysis_root"]
    fingerprint = snapshot["project_fingerprint"]
    if operation == "inspect":
        result = _inspect_zip(data, filename, analysis_root=root)
    elif operation == "graph":
        result = _graph_zip(data, filename, fingerprint, analysis_root=root)
    elif operation == "validate":
        result = _validate_zip(data, filename, fields["change"], fingerprint, analysis_root=root)
    elif operation in {"analyze", "reports"}:
        result = _analyze_zip(data, filename, fields["change"], fingerprint, analysis_root=root)
    elif operation == "source":
        result = _source(data, filename, fields.get("path"), fingerprint, root)
    elif operation == "questions":
        result = _question(data, filename, fields["change"], fields["question"],
                           fields.get("finding_index"), fields.get("history", "[]"), fingerprint, root)
    else:
        result = _suggestions(data, filename, fields["change"], fields.get("finding_index"), fingerprint, root)

    if isinstance(result, JSONResponse):
        if result.status_code != 200:
            return result
        result = json.loads(result.body)
    # Function reports previously omitted the ZIP identity. Snapshot responses
    # always include it, independently of the report's source-file hashes.
    result.update(project_id=snapshot["project_id"], project_snapshot_id=snapshot["id"],
                  project_fingerprint=fingerprint)
    if operation == "inspect":
        result["snapshot"] = snapshot
    if operation == "reports":
        if "project_name" not in result:
            from openimpact.storage import get_project
            result["project_name"] = get_project(snapshot["project_id"])["name"]
        record = save_report(result, source_filename=filename, analysis_root=root)
        return {"record": record, "report": result}
    return result


@router.post("/api/v1/snapshots/{snapshot_id}/{operation}")
async def snapshot_operation(snapshot_id: str, operation: str, request: Request):
    from openimpact.api import _error

    if operation not in _FIELDS:
        return _error(404, "operation_not_found", "没有找到该快照操作。")
    if not re.fullmatch(r"[0-9a-f]{32}", snapshot_id):
        return _error(404, "snapshot_not_found", "没有找到该项目快照。")
    form = await request.form()
    try:
        items = form.multi_items()
        keys = [key for key, _ in items]
        required, optional = _FIELDS[operation]
        if (request.query_params or set(keys) - required - optional - {"expected_fingerprint"}
                or len(set(keys)) != len(keys) or any(not isinstance(value, str) for _, value in items)):
            return _error(400, "unsupported_input", "快照请求包含重复或不支持的字段。")
        fields = dict(items)
        if not required <= fields.keys():
            return _error(422, "invalid_request", "快照请求缺少必要字段。")
        expected = fields.get("expected_fingerprint")
        if ((operation != "inspect" or expected is not None)
                and (not isinstance(expected, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", expected))):
            return _error(422, "invalid_fingerprint", "请提供当前项目快照的有效指纹。")
        return await run_in_threadpool(_run_snapshot, snapshot_id, operation, fields)
    except (SnapshotError, ZipInspectionError) as error:
        return _error(error.status_code, error.code, str(error))
    except AnalysisRootError as error:
        return _error(422, error.code, str(error))
    except (OSError, sqlite3.Error):
        return _error(503, "snapshot_unavailable", "本地项目快照或数据库暂时不可用。")
    finally:
        await form.close()
