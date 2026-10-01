"""HTTP access to the fixed demo and bounded ZIP-based project services."""

import hashlib
import re
from collections import deque
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from openimpact.analysis.change_file import ChangeFileError, load_change_spec
from openimpact.analysis.change_spec import validate_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.api_change import ChangeConfigError, build_change_spec, parse_change_config
from openimpact.repository import zip_inspector

_DEMO_DIR = Path(__file__).resolve().parents[2] / "examples" / "signature_change"
_DEMO_CHANGE = _DEMO_DIR / "change.json"

app = FastAPI(title="Nexus OpenImpact Demo API", version="0.1.0")


class _ZipBodyLimit:
    """Bound multipart bytes before FastAPI's form parser can spool the upload."""

    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] != "POST"
                or scope["path"] not in {"/api/v1/projects/inspect", "/api/v1/changes/validate"}):
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
    return JSONResponse(status_code=status, content={
        "project_name": report["project_name"],
        "project_fingerprint": report["project_fingerprint"],
        "coverage": report["coverage"],
        "change_spec": asdict(spec) if spec is not None else None,
        "validation": {"valid": valid, "diagnostics": diagnostics},
        "diagnostics": report["diagnostics"],
    })


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.post("/api/v1/projects/inspect")
async def inspect_project(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    form_items = (await request.form()).multi_items()
    if request.query_params or len(form_items) != 1 or form_items[0][0] != "file":
        await file.close()
        return _error(400, "unsupported_input", "仅接受名为 file 的 ZIP 文件字段。")

    try:
        data = await _read_zip(file)
        result = zip_inspector.inspect_python_zip(data, file.filename)
    except zip_inspector.ZipInspectionError as error:
        return _error(error.status_code, error.code, str(error))
    except OSError:
        return _error(503, "inspection_unavailable", "临时导入或源码读取失败。")
    finally:
        await file.close()
    return JSONResponse(content=result)


@app.post("/api/v1/changes/validate")
async def validate_change(
    request: Request,
    file: UploadFile = File(...),
    change: str = Form(...),
    expected_fingerprint: str | None = Form(None),
) -> JSONResponse:
    items = (await request.form()).multi_items()
    keys = [key for key, _ in items]
    if (request.query_params or keys.count("file") != 1 or keys.count("change") != 1
            or keys.count("expected_fingerprint") > 1
            or set(keys) - {"file", "change", "expected_fingerprint"}):
        await file.close()
        return _error(400, "unsupported_input", "仅接受 file、change 和可选 expected_fingerprint。")
    if expected_fingerprint is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", expected_fingerprint):
        await file.close()
        return _error(422, "invalid_fingerprint", "expected_fingerprint 必须是 SHA-256 十六进制值。")

    try:
        data = await _read_zip(file)
        fingerprint = hashlib.sha256(data).hexdigest()
        if expected_fingerprint is not None and fingerprint != expected_fingerprint.lower():
            return _error(409, "fingerprint_mismatch", "ZIP 指纹与此前 inspect 结果不一致。")
        with zip_inspector.indexed_python_zip(data, file.filename) as (index, report):
            try:
                config = parse_change_config(change)
                spec = build_change_spec(index, config)
            except ChangeConfigError as error:
                return _validation_response(report, None, False, [
                    {"code": error.code, "message": str(error)}
                ], 422)
            validation = validate_change_spec(index, spec)
            diagnostics = [asdict(item) for item in validation.diagnostics]
            return _validation_response(
                report, spec, validation.valid, diagnostics, 200 if validation.valid else 422
            )
    except zip_inspector.ZipInspectionError as error:
        return _error(error.status_code, error.code, str(error))
    except OSError:
        return _error(503, "inspection_unavailable", "临时导入或源码读取失败。")
    finally:
        await file.close()


@app.post("/api/v1/demo/analyze")
async def analyze_demo(request: Request) -> JSONResponse:
    if request.query_params or await request.body():
        return _error(400, "unsupported_input", "Demo 接口不接受项目路径、查询参数或请求体。")

    try:
        change = load_change_spec(_DEMO_CHANGE)
        report = build_report(analyze_project(_DEMO_DIR, change))
    except (ChangeFileError, OSError):
        return _error(503, "demo_unavailable", "内置 Demo 文件不可用，无法完成分析。")

    if not report["validation"]["valid"]:
        return _error(503, "demo_invalid", "内置 Demo 的 ChangeSpec 校验未通过。")
    return JSONResponse(content=report)
