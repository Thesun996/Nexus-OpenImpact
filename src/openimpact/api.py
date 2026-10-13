"""HTTP access to the fixed demo and bounded ZIP-based project services."""

import hashlib
import json
import logging
import re
import sqlite3
from collections import deque
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from openimpact.analysis.change_file import ChangeFileError, load_change_spec
from openimpact.analysis.change_spec import ChangeSpec, validate_change_spec
from openimpact.analysis.change_domain import parse_domain_config
from openimpact.analysis.module_change import ModuleChangeSpec, ModuleChangeError, build_module_change
from openimpact.analysis.module_facts import ModuleInventory
from openimpact.analysis.module_pipeline import analyze_module_project
from openimpact.analysis.module_report import build_module_report
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.analysis.symbol_index import SymbolIndex
from openimpact.analysis.variable_symbols import VariableInventory
from openimpact.analysis.symbol_change import SymbolChangeSpec, SymbolChangeError, build_symbol_change
from openimpact.analysis.symbol_impact import analyze_symbol_project
from openimpact.analysis.symbol_report import build_symbol_report
from openimpact.api_change import ChangeConfigError, build_change_spec, parse_change_config
from openimpact.repository import zip_inspector
from openimpact.repository.layout import AnalysisRootError
from openimpact.storage import delete_report, get_report, list_reports, save_report

_DEMO_DIR = Path(__file__).resolve().parents[2] / "examples" / "signature_change"
_DEMO_CHANGE = _DEMO_DIR / "change.json"
_LOGGER = logging.getLogger(__name__)

app = FastAPI(title="Nexus OpenImpact Demo API", version="0.1.0")


class _ZipBodyLimit:
    """Bound multipart bytes before FastAPI's form parser can spool the upload."""

    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] != "POST"
                or scope["path"] not in {
                    "/api/v1/projects/inspect", "/api/v1/changes/validate",
                    "/api/v1/projects/analyze",
                    "/api/v1/reports",
                    "/api/v1/projects/source", "/api/v1/reports/questions",
                    "/api/v1/reports/question-suggestions",
                }):
            await self.application(scope, receive, send)
            return

        limit = zip_inspector.MAX_UPLOAD_BYTES + 64 * 1024
        messages = deque()
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                messages.append(message)
                break
            size += len(message.get("body", b""))
            if size > limit:
                response = _error(413, "zip_limit_exceeded", "HTTP 上传请求体超过限制。")
                await response(scope, receive, send)
                return
            messages.append(message)
            if not message.get("more_body", False):
                break

        async def replay():
            if messages:
                return messages.popleft()
            return await receive()

        await self.application(scope, replay, send)


app.add_middleware(_ZipBodyLimit)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.exception_handler(Exception)
async def unexpected_error(_request: Request, _exception: Exception) -> JSONResponse:
    # Do not copy unexpected exception text, credentials, or paths into responses/logs.
    _LOGGER.error("Unexpected backend request failure")
    return _error(500, "internal_error", "后端请求处理失败，请重试。")


async def _read_zip(file: UploadFile) -> bytes:
    data = bytearray()
    while chunk := await file.read(64 * 1024):
        data.extend(chunk)
        if len(data) > zip_inspector.MAX_UPLOAD_BYTES:
            raise zip_inspector.ZipInspectionError(
                "zip_limit_exceeded", "ZIP 上传大小超过限制。", 413
            )
    return bytes(data)


def _validation_response(
    report: dict, spec, valid: bool, diagnostics: list[dict], status: int
) -> JSONResponse:
    module = isinstance(spec, ModuleChangeSpec) or report.get("change_domain") == "module"
    symbol = isinstance(spec, SymbolChangeSpec) or report.get("change_domain") == "symbol"
    return JSONResponse(status_code=status, content={
        **({"analysis_layout": report["analysis_layout"]} if "analysis_layout" in report else {}),
        **({"change_domain": "symbol" if symbol else "module"} if module or symbol else {}),
        "project_name": report["project_name"],
        "project_fingerprint": report["project_fingerprint"],
        "coverage": report["symbol_coverage"] if symbol else report["module_coverage"] if module else report["coverage"],
        "change_spec": spec.to_dict(include_operation=False) if spec is not None else None,
        "validation": {"valid": valid, "diagnostics": diagnostics},
        "diagnostics": report["symbol_diagnostics"] if symbol else report["module_diagnostics"] if module else report["diagnostics"],
    })


async def _change_input_error(
    request: Request, file: UploadFile, expected_fingerprint: str | None
) -> JSONResponse | None:
    items = (await request.form()).multi_items()
    keys = [key for key, _ in items]
    if (request.query_params or keys.count("file") != 1 or keys.count("change") != 1
            or keys.count("expected_fingerprint") > 1
            or keys.count("analysis_root") > 1
            or set(keys) - {"file", "change", "expected_fingerprint", "analysis_root"}):
        await file.close()
        return _error(400, "unsupported_input", "仅接受 file、change 和可选 expected_fingerprint、analysis_root。")
    if expected_fingerprint is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", expected_fingerprint):
        await file.close()
        return _error(422, "invalid_fingerprint", "expected_fingerprint 必须是 SHA-256 十六进制值。")
    return None


def _fingerprint_error(data: bytes, expected_fingerprint: str | None) -> JSONResponse | None:
    if (expected_fingerprint is not None
            and hashlib.sha256(data).hexdigest() != expected_fingerprint.lower()):
        return _error(409, "fingerprint_mismatch", "ZIP 指纹与此前 inspect 结果不一致。")
    return None


def _validated_spec(
    index: SymbolIndex, report: dict, change: str
) -> ChangeSpec | ModuleChangeSpec | JSONResponse:
    try:
        domain, config = parse_domain_config(change)
        if domain == "symbol":
            report["change_domain"] = "symbol"
            modules = ModuleInventory.from_index(index, tuple(report["module_inventory"]["occupied_names"]))
            return build_symbol_change(VariableInventory.from_index(index, modules), config)
        if domain == "module":
            report["change_domain"] = "module"
            inventory = ModuleInventory.from_index(index, tuple(report["module_inventory"]["occupied_names"]))
            return build_module_change(inventory, config)
        # Explicit function domain is additive; the legacy builder stays authoritative.
        config.pop("change_domain", None)
        config = parse_change_config(json.dumps(config))
        spec = build_change_spec(index, config)
    except (ChangeConfigError, ModuleChangeError, SymbolChangeError) as error:
        return _validation_response(report, None, False, [
            {"code": error.code, "message": str(error)}
        ], 422)
    validation = validate_change_spec(index, spec)
    if not validation.valid:
        return _validation_response(
            report, spec, False, [asdict(item) for item in validation.diagnostics], 422
        )
    return spec


def _inspect_zip(data: bytes, filename: str | None, *, analysis_root: str = ".") -> JSONResponse:
    return JSONResponse(content=zip_inspector.inspect_python_zip(data, filename, analysis_root=analysis_root))


def _validate_zip(
    data: bytes, filename: str | None, change: str, expected_fingerprint: str | None, *, analysis_root: str = "."
) -> JSONResponse:
    if error := _fingerprint_error(data, expected_fingerprint):
        return error
    with zip_inspector.indexed_python_zip(data, filename, analysis_root=analysis_root) as (index, report):
        spec = _validated_spec(index, report, change)
        if isinstance(spec, JSONResponse):
            return spec
        return _validation_response(report, spec, True, [], 200)


def _analyze_zip(
    data: bytes, filename: str | None, change: str, expected_fingerprint: str | None, *, analysis_root: str = "."
) -> JSONResponse:
    """Keep the snapshot, validation, report, and cleanup inside one worker call."""
    if error := _fingerprint_error(data, expected_fingerprint):
        return error
    with zip_inspector.indexed_python_zip(data, filename, analysis_root=analysis_root) as (index, inspect_report):
        spec = _validated_spec(index, inspect_report, change)
        if isinstance(spec, JSONResponse):
            return spec
        try:
            if isinstance(spec, SymbolChangeSpec):
                modules = ModuleInventory.from_index(index, tuple(inspect_report["module_inventory"]["occupied_names"]))
                inventory = VariableInventory.from_index(index, modules)
                report = build_symbol_report(analyze_symbol_project(index, spec, inventory))
                report["project_fingerprint"] = inspect_report["project_fingerprint"]
                report["project_name"] = inspect_report["project_name"]
                if "analysis_layout" in inspect_report:
                    report["analysis_layout"] = inspect_report["analysis_layout"]
                return JSONResponse(content=report)
            if isinstance(spec, ModuleChangeSpec):
                inventory = ModuleInventory.from_index(index, tuple(inspect_report["module_inventory"]["occupied_names"]))
                report = build_module_report(analyze_module_project(index, spec, inventory))
                report["project_fingerprint"] = inspect_report["project_fingerprint"]
                report["project_name"] = inspect_report["project_name"]
                if "analysis_layout" in inspect_report:
                    report["analysis_layout"] = inspect_report["analysis_layout"]
                return JSONResponse(content=report)
            report = build_report(analyze_project(index.scanner.project_path, spec,
                **({"analysis_root": index.analysis_root} if index.analysis_root != "." else {})))
            if not report["validation"]["valid"]:
                raise RuntimeError("Validated ChangeSpec failed against the same project snapshot")
            report["project_path"] = "."
            for item in report["diagnostics"]["parse_errors"]:
                if item["kind"] == "read_error":
                    item["message"] = "无法读取项目源文件。"
                elif item["kind"] == "encoding_error":
                    item["message"] = "项目源文件编码无法解析。"
            if report["coverage"]["status"] == "partial":
                report["coverage"]["message"] = (
                    "分析范围不完整；结果仅覆盖已成功解析的代码，未报告影响不能视为确定无影响。"
                )
            return JSONResponse(content=report)
        except Exception:
            _LOGGER.exception("Uploaded project analysis failed")
            return _error(500, "analysis_failed", "项目影响分析失败，请重试。")


def _analyze_and_save_zip(
    data: bytes, filename: str | None, change: str, expected_fingerprint: str | None, *, analysis_root: str = "."
) -> JSONResponse:
    response = _analyze_zip(data, filename, change, expected_fingerprint, analysis_root=analysis_root)
    if response.status_code != 200:
        return response
    report = json.loads(response.body.decode("utf-8"))
    if "project_name" not in report or "project_fingerprint" not in report:
        inspection = zip_inspector.inspect_python_zip(data, filename, analysis_root=analysis_root)
        report = {
            **report,
            "project_name": inspection["project_name"],
            "project_fingerprint": inspection["project_fingerprint"],
            **({"analysis_layout": inspection["analysis_layout"]} if "analysis_layout" in inspection else {}),
        }
    try:
        record = save_report(report, source_filename=filename, analysis_root=analysis_root)
    except (OSError, sqlite3.Error):
        _LOGGER.exception("Report persistence failed")
        return _error(503, "database_unavailable", "分析完成，但报告无法写入本地数据库。")
    return JSONResponse(content={"record": record, "report": report})


def _demo_report() -> JSONResponse:
    change = load_change_spec(_DEMO_CHANGE)
    report = build_report(analyze_project(_DEMO_DIR, change))
    if not report["validation"]["valid"]:
        return _error(503, "demo_invalid", "内置 Demo 的 ChangeSpec 校验未通过。")
    report["project_path"] = "."
    return JSONResponse(content=report)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.post("/api/v1/projects/inspect")
async def inspect_project(request: Request, file: UploadFile = File(...), analysis_root: str = Form(".")) -> JSONResponse:
    form_items = (await request.form()).multi_items()
    keys = [key for key, _ in form_items]
    if (request.query_params or keys.count("file") != 1 or keys.count("analysis_root") > 1
            or set(keys) - {"file", "analysis_root"}):
        await file.close()
        return _error(400, "unsupported_input", "仅接受 file ZIP 文件及可选 analysis_root 字段。")

    try:
        analysis_root = (await request.form()).get("analysis_root", analysis_root)
        data = await _read_zip(file)
        return await run_in_threadpool(_inspect_zip, data, file.filename,
                                      **({"analysis_root": analysis_root} if analysis_root != "." else {}))
    except AnalysisRootError as error:
        return _error(422, error.code, str(error))
    except zip_inspector.ZipInspectionError as error:
        return _error(error.status_code, error.code, str(error))
    except OSError:
        return _error(503, "inspection_unavailable", "临时导入或源码读取失败。")
    finally:
        await file.close()


@app.post("/api/v1/changes/validate")
async def validate_change(
    request: Request,
    file: UploadFile = File(...),
    change: str = Form(...),
    expected_fingerprint: str | None = Form(None),
    analysis_root: str = Form("."),
) -> JSONResponse:
    if error := await _change_input_error(request, file, expected_fingerprint):
        return error

    try:
        analysis_root = (await request.form()).get("analysis_root", analysis_root)
        data = await _read_zip(file)
        return await run_in_threadpool(_validate_zip, data, file.filename, change, expected_fingerprint,
                                      **({"analysis_root": analysis_root} if analysis_root != "." else {}))
    except AnalysisRootError as error:
        return _error(422, error.code, str(error))
    except zip_inspector.ZipInspectionError as error:
        return _error(error.status_code, error.code, str(error))
    except OSError:
        return _error(503, "inspection_unavailable", "临时导入或源码读取失败。")
    finally:
        await file.close()


@app.post("/api/v1/projects/analyze")
async def analyze_uploaded_project(
    request: Request,
    file: UploadFile = File(...),
    change: str = Form(...),
    expected_fingerprint: str | None = Form(None),
    analysis_root: str = Form("."),
) -> JSONResponse:
    if error := await _change_input_error(request, file, expected_fingerprint):
        return error

    try:
        analysis_root = (await request.form()).get("analysis_root", analysis_root)
        data = await _read_zip(file)
        return await run_in_threadpool(_analyze_zip, data, file.filename, change, expected_fingerprint,
                                      **({"analysis_root": analysis_root} if analysis_root != "." else {}))
    except AnalysisRootError as error:
        return _error(422, error.code, str(error))
    except zip_inspector.ZipInspectionError as error:
        return _error(error.status_code, error.code, str(error))
    except OSError:
        return _error(503, "inspection_unavailable", "临时导入或源码读取失败。")
    finally:
        await file.close()


@app.post("/api/v1/reports")
async def analyze_and_save_report(
    request: Request,
    file: UploadFile = File(...),
    change: str = Form(...),
    expected_fingerprint: str | None = Form(None),
    analysis_root: str = Form("."),
) -> JSONResponse:
    if error := await _change_input_error(request, file, expected_fingerprint):
        return error

    try:
        analysis_root = (await request.form()).get("analysis_root", analysis_root)
        data = await _read_zip(file)
        return await run_in_threadpool(_analyze_and_save_zip, data, file.filename, change, expected_fingerprint,
                                      **({"analysis_root": analysis_root} if analysis_root != "." else {}))
    except AnalysisRootError as error:
        return _error(422, error.code, str(error))
    except zip_inspector.ZipInspectionError as error:
        return _error(error.status_code, error.code, str(error))
    except OSError:
        return _error(503, "inspection_unavailable", "临时导入或源码读取失败。")
    finally:
        await file.close()


@app.get("/api/v1/reports")
def saved_reports(limit: int = 20, offset: int = 0) -> JSONResponse:
    if limit < 1 or limit > 50 or offset < 0:
        return _error(422, "invalid_pagination", "limit 必须在 1 到 50 之间，offset 不能为负数。")
    try:
        return JSONResponse(content={"items": list_reports(limit=limit, offset=offset), "limit": limit, "offset": offset})
    except (OSError, sqlite3.Error):
        _LOGGER.exception("Report list failed")
        return _error(503, "database_unavailable", "本地数据库暂时不可用。")


@app.get("/api/v1/reports/{report_id}")
def saved_report(report_id: str) -> JSONResponse:
    if not re.fullmatch(r"[0-9a-f]{32}", report_id):
        return _error(404, "report_not_found", "没有找到该历史报告。")
    try:
        record = get_report(report_id)
    except (OSError, sqlite3.Error):
        _LOGGER.exception("Report read failed")
        return _error(503, "database_unavailable", "本地数据库暂时不可用。")
    if record is None:
        return _error(404, "report_not_found", "没有找到该历史报告。")
    return JSONResponse(content=record)


@app.delete("/api/v1/reports/{report_id}")
def delete_saved_report(report_id: str) -> JSONResponse:
    if not re.fullmatch(r"[0-9a-f]{32}", report_id):
        return _error(404, "report_not_found", "没有找到该历史报告。")
    try:
        deleted = delete_report(report_id)
    except (OSError, sqlite3.Error):
        _LOGGER.exception("Report delete failed")
        return _error(503, "database_unavailable", "本地数据库暂时不可用。")
    if not deleted:
        return _error(404, "report_not_found", "没有找到该历史报告。")
    return JSONResponse(content={"deleted": True, "id": report_id})


@app.post("/api/v1/demo/analyze")
async def analyze_demo(request: Request) -> JSONResponse:
    if request.query_params or await request.body():
        return _error(400, "unsupported_input", "Demo 接口不接受项目路径、查询参数或请求体。")

    try:
        return await run_in_threadpool(_demo_report)
    except (ChangeFileError, OSError):
        return _error(503, "demo_unavailable", "内置 Demo 文件不可用，无法完成分析。")


from openimpact.workspace_api import router as workspace_router
app.include_router(workspace_router)
