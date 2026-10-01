"""Serialize an analysis run and render a concise Chinese terminal report."""

from dataclasses import asdict
from typing import Any

from openimpact.analysis.call_graph import CallEdge
from openimpact.analysis.pipeline import AnalysisRun


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


def build_report(run: AnalysisRun) -> dict[str, Any]:
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
    partial = bool(parse_errors or unresolved_calls or unresolved_imports
                   or run.index.ambiguous_modules or run.index.ambiguous_symbols)
    return {
        "schema_version": 1,
        "project_path": str(run.project_path),
        "change": asdict(run.change_spec),
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
        "manual_reviews": manual,
        "pre_existing_problems": pre_existing,
        "diagnostics": {
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
    change = report["change"]
    added = change["added_parameter"]
    summary = report["summary"]
    coverage = report["coverage"]
    lines = [
        "Nexus OpenImpact 分析报告",
        f"项目：{report['project_path']}",
        (f"变更：{change['target_symbol_id']} 新增必填参数 "
         f"{added['name']}（{added['kind']}）"),
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
    return "\n".join(lines)
