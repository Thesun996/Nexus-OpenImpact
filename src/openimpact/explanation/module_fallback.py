"""Rule-only explanation of existing import evidence; never infers dependencies."""

from openimpact.explanation.models import ExplanationResult
from openimpact.reporting.import_evidence import ImportEvidence
from openimpact.explanation.reference_fallback import explain_reference_evidence
from openimpact.reporting.import_evidence import import_site


def explain_module_evidence(evidence: ImportEvidence, *, run=None, finding=None) -> ExplanationResult:
    if evidence.status != "available" or not evidence.location or evidence.source_snippet is None:
        raise ValueError("模块证据不可用，不能生成对应解释。")
    if run is not None and finding is not None:
        source_id = min(evidence.propagation_path,
            key=lambda path: (len(path['modules']), path['source_direct_impact']))['source_direct_impact']
        direct = next(item for item in run.direct if item.finding_id == source_id)
        reference = direct.assessment.before
        descriptor = run.inventory.get(reference.source_module)
        return explain_reference_evidence(evidence.to_dict(), run.change_spec.to_dict(),
            {'location': import_site(reference), 'import_expression': reference.syntax.source_text},
            direct.assessment.reason, run.index.scanner.project_path,
            descriptor.source_hash if descriptor else None)
    site = f"{evidence.location['file']}:{evidence.location['line']}"
    direct = evidence.impact_type == "direct_import"
    summary = (f"{site} 的项目内导入引用因拟定模块变更发生静态断裂。" if direct
               else f"{site} 位于 {evidence.target_module_id} 的上游模块依赖路径，建议检查。")
    paths = "；".join(" → ".join(path["modules"]) for path in evidence.propagation_path)
    return ExplanationResult(
        summary, f"{evidence.reason} 源码：{evidence.source_snippet.strip()}。依赖路径：{paths}。",
        "unknown", f"核对 {site} 的模块引用及兼容安排，在实际改动后自行执行相关测试。", 1.0,
    )
