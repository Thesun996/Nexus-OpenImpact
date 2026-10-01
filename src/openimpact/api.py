"""Minimal HTTP access to the repository's fixed signature-change demo."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from openimpact.analysis.change_file import ChangeFileError, load_change_spec
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report

_DEMO_DIR = Path(__file__).resolve().parents[2] / "examples" / "signature_change"
_DEMO_CHANGE = _DEMO_DIR / "change.json"

app = FastAPI(title="Nexus OpenImpact Demo API", version="0.1.0")


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


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
