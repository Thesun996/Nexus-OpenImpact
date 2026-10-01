"""HTTP access to the fixed demo and bounded ZIP syntax inspection."""

from collections import deque
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import JSONResponse

from openimpact.analysis.change_file import ChangeFileError, load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.repository import zip_inspector

_DEMO_DIR = Path(__file__).resolve().parents[2] / "examples" / "signature_change"
_DEMO_CHANGE = _DEMO_DIR / "change.json"

app = FastAPI(title="Nexus OpenImpact Demo API", version="0.1.0")


class _InspectBodyLimit:
    """Bound multipart bytes before FastAPI's form parser can spool the upload."""

    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/api/v1/projects/inspect":
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


app.add_middleware(_InspectBodyLimit)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.post("/api/v1/projects/inspect")
async def inspect_project(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    form_items = (await request.form()).multi_items()
    if request.query_params or len(form_items) != 1 or form_items[0][0] != "file":
        return _error(400, "unsupported_input", "仅接受名为 file 的 ZIP 文件字段。")

    data = bytearray()
    try:
        while chunk := await file.read(64 * 1024):
            data.extend(chunk)
            if len(data) > zip_inspector.MAX_UPLOAD_BYTES:
                return _error(413, "zip_limit_exceeded", "ZIP 上传大小超过限制。")
        result = zip_inspector.inspect_python_zip(bytes(data), file.filename)
    except zip_inspector.ZipInspectionError as error:
        return _error(error.status_code, error.code, str(error))
    except OSError:
        return _error(503, "inspection_unavailable", "临时导入或源码读取失败。")
    finally:
        await file.close()
    return JSONResponse(content=result)


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
