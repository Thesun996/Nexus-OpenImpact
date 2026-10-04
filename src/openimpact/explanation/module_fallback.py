"""Rule-only explanation of existing import evidence; never infers dependencies."""

from openimpact.explanation.models import ExplanationResult
from openimpact.reporting.import_evidence import ImportEvidence


def explain_module_evidence(evidence: ImportEvidence) -> ExplanationResult:
    if evidence.status != "available" or not evidence.location or evidence.source_snippet is None:
        raise ValueError("模块证据不可用，不能生成对应解释。")
    site = f"{evidence.location['file']}:{evidence.location['line']}"
    direct = evidence.impact_type == "direct_import"
    summary = (f"{site} 的项目内导入引用因拟定模块变更发生静态断裂。" if direct
               else f"{site} 位于 {evidence.target_module_id} 的上游模块依赖路径，建议检查。")
    paths = "；".join(" → ".join(path["modules"]) for path in evidence.propagation_path)
    return ExplanationResult(
        summary, f"{evidence.reason} 源码：{evidence.source_snippet.strip()}。依赖路径：{paths}。",
        "unknown", f"核对 {site} 的模块引用及兼容安排，在实际改动后自行执行相关测试。", 1.0,
    )
