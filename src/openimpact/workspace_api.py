"""Read-only source browsing and report questions over isolated ZIP snapshots."""

import hashlib
import io
from pathlib import PurePosixPath
import tokenize

from fastapi import APIRouter, File, Form, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from openimpact.analysis.module_facts import ModuleInventory
from openimpact.analysis.module_pipeline import analyze_module_project
from openimpact.analysis.module_report import build_module_report
from openimpact.analysis.pipeline import analyze_project
from openimpact.analysis.report import build_report
from openimpact.analysis.symbol_impact import analyze_symbol_project
from openimpact.analysis.symbol_report import build_symbol_report
from openimpact.analysis.module_change import ModuleChangeSpec
from openimpact.analysis.symbol_change import SymbolChangeSpec
from openimpact.analysis.variable_symbols import VariableInventory
from openimpact.explanation.fallback import RuleBasedProvider
from openimpact.repository import zip_inspector
from openimpact.repository.layout import AnalysisRootError
from openimpact.reporting.questions import answer_question, question_context, question_history, suggest_questions

router = APIRouter()


def _source(data, filename, path, expected, analysis_root):
    from openimpact.api import _error, _fingerprint_error
    if error := _fingerprint_error(data, expected):
        return error
    if path is not None and (not path or "\\" in path or ":" in path or "\x00" in path
            or PurePosixPath(path).is_absolute() or any(part in {".", "..", ""} for part in path.split("/"))
            or not path.endswith(".py")):
        return _error(422, "invalid_source_path", "请选择项目内的 Python 相对文件路径。")
    with zip_inspector.indexed_python_zip(data, filename, analysis_root=analysis_root) as (index, inspection):
        root = index.scanner.project_path
        paths = {item.as_posix(): root / item for item in index.scanner.scan()}
        if path is not None and path not in paths:
            return _error(404, "source_not_found", "当前项目中没有该 Python 文件。")
        files = []
        selected = None
        for name, item in sorted(paths.items()):
            raw = item.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            files.append({"path": name, "size_bytes": len(raw), "source_hash": digest})
            if name == path:
                try:
                    encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
                    text = raw.decode(encoding)
                except (SyntaxError, UnicodeError, LookupError):
                    return _error(422, "source_encoding_error", "该文件的 Python 源码编码无法读取。")
                selected = {"path": name, "content": text, "encoding": encoding,
                            "source_hash": digest, "line_count": len(text.splitlines())}
        return {"project_fingerprint": inspection["project_fingerprint"], "project_name": inspection["project_name"],
                "files": files, "file": selected, "read_only": True,
                "message": "文件可阅读不代表已完整分析；源码仅在本次请求内读取，不执行或修改。"}


def _question(data, filename, change, question, finding_index, history, expected, analysis_root, *, recommendations=False):
    from openimpact.api import _error, _fingerprint_error, _validated_spec
    from fastapi.responses import JSONResponse
    if error := _fingerprint_error(data, expected):
        return error
    if not recommendations and (not question.strip() or len(question) > 1000):
        return _error(422, "invalid_question", "问题不能为空，且不能超过 1000 个字符。")
    try:
        history = question_history(history)
        if finding_index is not None and (not finding_index.isascii() or not finding_index.isdecimal()):
            raise ValueError("影响记录索引必须是非负整数。")
        slot = int(finding_index) if finding_index is not None else None
    except ValueError as error:
        return _error(422, "invalid_question_context", str(error))
    with zip_inspector.indexed_python_zip(data, filename, analysis_root=analysis_root) as (index, inspection):
        spec = _validated_spec(index, inspection, change)
        if isinstance(spec, JSONResponse):
            return spec
        # Generate authoritative facts without asking the model once per finding.
        # Only the user's explicit question/recommendation request invokes a model, at most once.
        if isinstance(spec, SymbolChangeSpec):
            modules = ModuleInventory.from_index(index, tuple(inspection["module_inventory"]["occupied_names"]))
            report = build_symbol_report(analyze_symbol_project(index, spec, VariableInventory.from_index(index, modules)))
        elif isinstance(spec, ModuleChangeSpec):
            modules = ModuleInventory.from_index(index, tuple(inspection["module_inventory"]["occupied_names"]))
            report = build_module_report(analyze_module_project(index, spec, modules))
        else:
            report = build_report(analyze_project(index.scanner.project_path, spec,
                **({"analysis_root": index.analysis_root} if index.analysis_root != "." else {})),
                explanation_provider=RuleBasedProvider())
        try:
            context = question_context(report, slot)
        except ValueError as error:
            return _error(422, "invalid_question_context", str(error))
        result = suggest_questions(context) if recommendations else answer_question(context, question.strip(), history)
        return {**result,
                "project_fingerprint": inspection["project_fingerprint"], "finding_index": slot,
                "change_domain": context["change_domain"], "coverage": report["coverage"],
                "scope": "current_change_report"}


def _suggestions(data, filename, change, finding_index, expected, analysis_root):
    return _question(data, filename, change, "", finding_index, "[]", expected, analysis_root, recommendations=True)


async def _request(request, file, expected, root, operation, fields, allowed):
    from openimpact.api import _error, _read_zip
    import re
    try:
        keys = [key for key, _ in (await request.form()).multi_items()]
        if request.query_params or set(keys) - allowed or any(keys.count(key) != 1 for key in keys):
            return _error(400, "unsupported_input", "请求字段重复或包含不支持的输入。")
        if not isinstance(expected, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", expected):
            return _error(422, "invalid_fingerprint", "请提供当前 ZIP 的有效项目指纹。")
        data = await _read_zip(file)
        return await run_in_threadpool(operation, data, file.filename, *fields, expected, root)
    except AnalysisRootError as error:
        return _error(422, error.code, str(error))
    except zip_inspector.ZipInspectionError as error:
        return _error(error.status_code, error.code, str(error))
    except OSError:
        return _error(503, "source_unavailable", "临时项目源码无法读取，请重试。")
    except Exception:
        return _error(500, "workspace_failed", "源码阅读或报告追问处理失败，请重试。")
    finally:
        await file.close()


@router.post("/api/v1/projects/source")
async def project_source(request: Request, file: UploadFile = File(...), expected_fingerprint: str = Form(...),
                         path: str | None = Form(None), analysis_root: str = Form(".")):
    return await _request(request, file, expected_fingerprint, analysis_root, _source, (path,),
                          {"file", "expected_fingerprint", "path", "analysis_root"})


@router.post("/api/v1/reports/questions")
async def report_question(request: Request, file: UploadFile = File(...), change: str = Form(...),
                          question: str = Form(...), expected_fingerprint: str = Form(...),
                          finding_index: str | None = Form(None), history: str = Form("[]"), analysis_root: str = Form(".")):
    return await _request(request, file, expected_fingerprint, analysis_root, _question,
                          (change, question, finding_index, history),
                          {"file", "change", "question", "expected_fingerprint", "finding_index", "history", "analysis_root"})


@router.post("/api/v1/reports/question-suggestions")
async def report_question_suggestions(request: Request, file: UploadFile = File(...), change: str = Form(...),
                                      expected_fingerprint: str = Form(...), finding_index: str | None = Form(None),
                                      analysis_root: str = Form(".")):
    return await _request(request, file, expected_fingerprint, analysis_root, _suggestions, (change, finding_index),
                          {"file", "change", "expected_fingerprint", "finding_index", "analysis_root"})
