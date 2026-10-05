"""Serialize an analysis run and render a concise Chinese terminal report."""

from dataclasses import asdict, replace
import logging
from pathlib import Path
from typing import Any

from openimpact.analysis.call_graph import CallEdge
from openimpact.analysis.change_file import change_spec_from_dict
from openimpact.analysis.change_spec import ChangeSpec
from openimpact.analysis.direct_impact import ImpactFinding
from openimpact.analysis.indirect_impact import IndirectImpactFinding
from openimpact.analysis.pipeline import AnalysisRun
from openimpact.explanation.models import ExplanationInput
from openimpact.explanation.context import build_explanation_context
from openimpact.explanation.provider import ExplanationProvider, explain_safely
from openimpact.reporting.evidence import EvidenceBuilder, ImpactEvidence
from openimpact.repository.layout import layout_metadata


_LOGGER = logging.getLogger(__name__)


def _edge_data(edge: CallEdge) -> dict[str, Any]:
    return {
        "caller_symbol_id": edge.caller_symbol_id,
        "callee_symbol_id": edge.callee_symbol_id,
        "file": edge.file.as_posix(),
        "line": edge.line,
        "column": edge.col_offset,
        "resolution_basis": edge.basis,
    }


def _call_data(assessment: Any) -> dict[str, Any]:
    return {
        "caller_symbol_id": assessment.caller_symbol_id,
        "target_symbol_id": assessment.target_symbol_id,
        "file": assessment.file.as_posix(),
        "line": assessment.line,
        "column": assessment.col_offset,
        "resolution_basis": assessment.resolution_basis,
        "before_status": assessment.before_status,
        "after_status": assessment.after_status,
        "before_reason": assessment.before_reason,
        "after_reason": assessment.after_reason,
        "effect": assessment.effect,
    }


def _evidence_data(evidence: ImpactEvidence) -> dict[str, Any]:
    location = evidence.location
    return {
        "impact_type": evidence.impact_type,
        "target_symbol": evidence.target_symbol,
        "location": (
            {"file": location.file.as_posix(), "line": location.line,
             "column": location.column, "end_line": location.end_line}
            if location is not None else None
        ),
        "source_snippet": evidence.source_snippet,
        "source_hash": evidence.source_hash,
        "rule": evidence.rule,
        "reason": evidence.reason,
        "propagation_path": [
            {
                "symbols": list(path.symbols),
                "call_sites": [
                    {"file": site.file.as_posix(), "line": site.line,
                     "column": site.column, "end_line": site.end_line}
                    for site in path.call_sites
                ],
                "direct_evidence_reference": path.direct_evidence_reference,
            }
            for path in evidence.propagation_path
        ],
        "call_expression": evidence.call_expression,
        "evidence_reference": evidence.evidence_reference,
        "status": "available" if evidence.source_snippet is not None
                  and not evidence.diagnostics else "unavailable",
        "diagnostics": [asdict(item) for item in evidence.diagnostics],
    }


def _finding_evidence(
    project_root: Path, finding: ImpactFinding | IndirectImpactFinding, change_spec: ChangeSpec
) -> tuple[dict[str, Any], ImpactEvidence | None]:
    reason = (change_spec.operation.evidence_reason(change_spec.target_symbol_id, finding.reason)
              if change_spec.operation is not None else finding.reason)
    try:
        evidence = EvidenceBuilder(project_root).build(finding)
        # Operation supplies intent wording only; source facts and the original
        # before/after compatibility conclusion remain unchanged.
        evidence = replace(evidence, reason=reason)
        return _evidence_data(evidence), evidence
    except Exception:
        # Evidence is supplementary; keep the already computed impact report usable.
        _LOGGER.exception("Evidence generation failed")
        target = (finding.assessment.target_symbol_id if isinstance(finding, ImpactFinding)
                  else finding.target_symbol or "")
        rule = (finding.rule_id if isinstance(finding, ImpactFinding)
                else "resolved_upstream_call_path")
        return {
            "impact_type": finding.impact_type,
            "target_symbol": target,
            "location": None,
            "source_snippet": None,
            "source_hash": None,
            "rule": rule,
            "reason": reason,
            "propagation_path": [],
            "call_expression": None,
            "evidence_reference": finding.evidence_reference,
            "status": "unavailable",
            "diagnostics": [{"code": "evidence_unavailable",
                             "message": "证据生成失败，影响分析结果仍可查看。"}],
        }, None


def _explanation_data(
    evidence_data: dict[str, Any], evidence: ImpactEvidence | None,
    change_description: str, provider: ExplanationProvider | None,
    run: AnalysisRun | None = None, finding: Any = None,
) -> dict[str, Any]:
    if evidence is None or evidence_data["status"] != "available":
        return {
            "evidence": evidence_data,
            "explanation": None,
            "diagnostics": [{"code": "evidence_unavailable",
                             "message": "源码证据不可用，无法生成解释。"}],
        }
    try:
        explanation_input = ExplanationInput.from_evidence(evidence, change_description)
        if run is not None and finding is not None:
            try:
                explanation_input = replace(explanation_input,
                    context=build_explanation_context(run, finding, evidence))
            except Exception:
                # Optional enrichment cannot suppress the base evidence explanation.
                _LOGGER.warning('Explanation context unavailable; using base evidence')
        explanation = explain_safely(explanation_input, provider)
        return {"evidence": evidence_data, "explanation": explanation.to_dict(),
                "diagnostics": []}
    except Exception:
        _LOGGER.exception("Explanation generation failed")
        return {
            "evidence": evidence_data,
            "explanation": None,
            "diagnostics": [{"code": "explanation_unavailable",
                             "message": "解释生成失败，源码证据和影响结果仍可查看。"}],
        }


def build_report(
    run: AnalysisRun, *, explanation_provider: ExplanationProvider | None = None
) -> dict[str, Any]:
    """Return JSON-ready facts, findings, coverage, and unresolved diagnostics."""
    direct = [
        {**_call_data(finding.assessment), "rule_id": finding.rule_id,
         "reason": finding.reason, "impact_type": "direct"}
        for finding in run.direct.findings if finding.effect == "direct_impact"
    ]
    manual = [
        {**_call_data(finding.assessment), "rule_id": finding.rule_id,
         "reason": finding.reason}
        for finding in run.direct.findings if finding.effect == "manual_review"
    ]
    pre_existing = [
        _call_data(item) for item in run.direct.assessments
        if item.effect == "pre_existing_problem"
    ]
    indirect = [
        {
            "impacted_symbol_id": finding.impacted_symbol_id,
            "impact_type": finding.impact_type,
            "graph_distance": finding.graph_distance,
            "certainty": finding.certainty,
            "reason": finding.reason,
            "sources": [
                {
                    "direct_call": _call_data(source.source_direct_impact.assessment),
                    "propagation_path": [_edge_data(edge) for edge in source.propagation_path],
                }
                for source in finding.sources
            ],
        }
        for finding in run.indirect.findings
    ]
    evidence_records = [
        _finding_evidence(run.project_path, finding, run.change_spec)
        for finding in run.direct.findings if finding.effect == "direct_impact"
    ] + [
        _finding_evidence(run.project_path, finding, run.change_spec)
        for finding in run.indirect.findings
    ]
    evidences = [item for item, _ in evidence_records]
    change_description = run.change_spec.describe()
    explanations = [
        _explanation_data(item, evidence, change_description, explanation_provider, run, finding)
        for (item, evidence), finding in zip(evidence_records,
            [item for item in run.direct.findings if item.effect == 'direct_impact']
            + list(run.indirect.findings))
    ]
    parse_errors = [
        {"file": path.as_posix(), "kind": diagnostic.kind,
         "message": diagnostic.message, "line": diagnostic.lineno,
         "column": diagnostic.col_offset}
        for path, diagnostics in sorted(run.index.parse_diagnostics.items())
        for diagnostic in diagnostics
    ]
    unresolved_calls = [
        {"file": call.file.as_posix(), "line": call.line,
         "column": call.call.col_offset, "expression": call.call.expression,
         "reason": call.reason}
        for call in run.graph.unresolved_calls
    ]
    unresolved_imports = [
        {"file": binding.source_file.as_posix(), "line": binding.lineno,
         "local_name": binding.local_name, "reason": binding.reason}
        for module in sorted(run.index.bindings)
        for binding in run.index.bindings[module].values()
        if binding.status == "unresolved"
    ]
    unsupported_scopes = run.index.unsupported_scope_diagnostics()
    partial = bool(parse_errors or unresolved_calls or unresolved_imports or unsupported_scopes
                   or run.index.ambiguous_modules or run.index.ambiguous_symbols)
    return {
        **({"analysis_layout": layout_metadata(run.index.analysis_root)}
           if run.index.analysis_root != "." else {}),
        "schema_version": 1,
        "project_path": str(run.project_path),
        "change": run.change_spec.to_dict(include_operation=False),
        "validation": {
            "valid": run.direct.validation.valid,
            "diagnostics": [asdict(item) for item in run.direct.validation.diagnostics],
        },
        "coverage": {
            "status": "partial" if partial else "complete",
            "indexed_modules": len(run.index.modules),
            "indexed_functions": len(run.index.symbols),
            "files_with_parse_errors": len(run.index.parse_diagnostics),
            "ambiguous_modules": sorted(run.index.ambiguous_modules),
            "ambiguous_symbols": sorted(run.index.ambiguous_symbols),
        },
        "summary": {
            "direct_impact_count": run.direct.direct_impact_count,
            "indirect_1hop_count": sum(item.impact_type == "indirect_1hop"
                                       for item in run.indirect.findings),
            "indirect_2hop_count": sum(item.impact_type == "indirect_2hop"
                                       for item in run.indirect.findings),
            "manual_review_count": len(manual),
            "pre_existing_problem_count": len(pre_existing),
            "unresolved_call_count": len(unresolved_calls),
        },
        "direct_impacts": direct,
        "indirect_impacts": indirect,
        "evidences": evidences,
        "explanations": explanations,
        "manual_reviews": manual,
        "pre_existing_problems": pre_existing,
        "diagnostics": {
            **({"unsupported_scopes": unsupported_scopes} if unsupported_scopes else {}),
            "parse_errors": parse_errors,
            "unresolved_calls": unresolved_calls,
            "unresolved_imports": unresolved_imports,
        },
    }


def _path_text(edges: list[dict[str, Any]]) -> str:
    return " → ".join([edges[0]["caller_symbol_id"],
                      *(edge["callee_symbol_id"] for edge in edges)])


def render_chinese_report(report: dict[str, Any]) -> str:
    """Render existing report facts without performing analysis."""
    change_description = change_spec_from_dict(report["change"]).describe()
    summary = report["summary"]
    coverage = report["coverage"]
    lines = [
        "Nexus OpenImpact 分析报告",
        f"项目：{report['project_path']}",
        f"变更：{change_description}",
        (f"覆盖：{coverage['status']}；索引模块 {coverage['indexed_modules']}，"
         f"函数 {coverage['indexed_functions']}，解析失败文件 "
         f"{coverage['files_with_parse_errors']}"),
    ]
    if not report["validation"]["valid"]:
        lines.append("ChangeSpec 校验失败：")
        lines.extend(f"- {item['code']}: {item['message']}"
                     for item in report["validation"]["diagnostics"])

    lines.append(f"Direct Impact（{summary['direct_impact_count']}）：")
    for item in report["direct_impacts"]:
        lines.append(f"- {item['caller_symbol_id']} → {item['target_symbol_id']} "
                     f"@ {item['file']}:{item['line']}:{item['column']}")
        lines.append(f"  {item['reason']}")

    for impact_type, title in (
        ("indirect_1hop", "1-hop Indirect"),
        ("indirect_2hop", "2-hop Indirect"),
    ):
        items = [item for item in report["indirect_impacts"]
                 if item["impact_type"] == impact_type]
        lines.append(f"{title}（{len(items)}）：")
        for item in items:
            lines.append(f"- {item['impacted_symbol_id']}：{item['reason']}")
            for source in item["sources"]:
                path = source["propagation_path"]
                lines.append(f"  路径：{_path_text(path)}")
                lines.append("  上游调用：" + f"{path[0]['file']}:{path[0]['line']}；"
                             + "Direct 证据："
                             + f"{path[-1]['file']}:{path[-1]['line']}:"
                             + f"{path[-1]['column']}")

    lines.append(f"人工检查（{summary['manual_review_count']}）：")
    for item in report["manual_reviews"]:
        lines.append(f"- {item['file']}:{item['line']} "
                     f"{item['caller_symbol_id']} → {item['target_symbol_id']}："
                     f"{item['reason']}")
    lines.append(f"既有问题（{summary['pre_existing_problem_count']}）：")
    for item in report["pre_existing_problems"]:
        lines.append(f"- {item['file']}:{item['line']} {item['caller_symbol_id']}："
                     "修改前已经不兼容，不计入本次影响。")
    diagnostics = report["diagnostics"]
    lines.append(
        "未解析／诊断："
        f"调用 {len(diagnostics['unresolved_calls'])}，"
        f"import {len(diagnostics['unresolved_imports'])}，"
        f"解析错误 {len(diagnostics['parse_errors'])}。"
    )
    for item in diagnostics["parse_errors"]:
        lines.append(f"- 解析 {item['file']}:{item['line'] or '?'} "
                     f"[{item['kind']}] {item['message']}")
    for item in diagnostics["unresolved_calls"]:
        lines.append(f"- 调用 {item['file']}:{item['line']} "
                     f"{item['expression']} [{item['reason']}]")
    for item in diagnostics["unresolved_imports"]:
        lines.append(f"- import {item['file']}:{item['line']} "
                     f"{item['local_name']} [{item['reason']}]")
    for item in diagnostics.get("unsupported_scopes", []):
        lines.append(f"- 分析范围 {item['file']}:{item['line']}：{item['message']}")
    return "\n".join(lines)
