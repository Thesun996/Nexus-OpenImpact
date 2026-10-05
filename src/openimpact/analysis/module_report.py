"""Independent Module report v1; signature report v1 fields are untouched."""

from dataclasses import asdict

from openimpact.explanation.module_fallback import explain_module_evidence
from openimpact.reporting.import_evidence import ImportEvidence, ImportEvidenceBuilder, import_site


def reference_data(reference):
    return {"reference_id": reference.reference_id, "source_module": reference.source_module,
            "location": import_site(reference), "import_type": reference.syntax.import_type,
            "declared_module": reference.syntax.module, "imported_name": reference.syntax.imported_name,
            "alias": reference.syntax.alias, "level": reference.syntax.level,
            "import_expression": reference.syntax.source_text, "scope": reference.syntax.scope,
            "status": reference.status, "target_module_id": reference.target_module_id, "reason": reference.reason}


def module_diagnostics(index, inventory, references):
    parse_errors = [{"file": file.as_posix(), "line": diagnostic.lineno, "column": diagnostic.col_offset,
                     "kind": diagnostic.kind,
                     "message": diagnostic.message if diagnostic.kind == "syntax_error" else "项目源码无法读取或解码。"}
                    for file, diagnostics in sorted(index.parse_diagnostics.items()) for diagnostic in diagnostics]
    syntax = [{"file": file.as_posix(), **asdict(diagnostic)} for file, parsed in sorted(index.parsed_files.items())
              for diagnostic in parsed.module_diagnostics]
    return {"parse_errors": parse_errors, "import_diagnostics": syntax,
            "unsupported_modules": [{"file": item.file, "module_id": item.module_id, "reason": item.reason}
                                    for item in inventory.modules if not item.selectable],
            "unresolved_imports": [reference_data(item) for item in references if item.status == "unresolved"],
            "manual_review_imports": [reference_data(item) for item in references if item.status == "manual_review"]}


def module_coverage(index, inventory, references):
    diagnostics = module_diagnostics(index, inventory, references)
    partial = any(diagnostics.values())
    return {"status": "partial" if partial else "complete", "analysis_scope": "project_root_static",
            "python_files": len(inventory.modules), "supported_modules": sum(item.selectable for item in inventory.modules),
            "message": "覆盖不完整；只报告已确认的静态引用，零影响不证明项目无其他影响。" if partial
                       else "已覆盖项目根下受支持的静态导入；不模拟运行时路径、外部同名提供者或初始化执行。"}


def build_module_report(run):
    references = tuple(item.before for item in run.assessments)
    diagnostics = module_diagnostics(run.index, run.inventory, references)
    direct = [{"finding_id": finding.finding_id, "impact_type": finding.impact_type,
               "target_module_id": finding.target_module_id, "impacted_module_id": finding.assessment.before.source_module,
               "reference_id": finding.assessment.before.reference_id, "location": import_site(finding.assessment.before),
               "before_resolution": reference_data(finding.assessment.before), "after_resolution": reference_data(finding.assessment.after),
               "certainty": "definite_project_reference_break", "rule": finding.rule, "reason": finding.assessment.reason}
              for finding in run.direct]
    indirect = [{"finding_id": finding.finding_id, "impact_type": finding.impact_type,
                 "impacted_module_id": finding.impacted_module_id, "target_module_id": finding.target_module_id,
                 "hop": finding.hop, "graph_distance": finding.graph_distance, "certainty": finding.certainty,
                 "reason": finding.reason, "source_direct_impacts": [source.source_direct_impact for source in finding.sources],
                 "propagation_path": [{"modules": [source.path[0].importer_module_id, *(edge.target_module_id for edge in source.path)],
                                       "import_sites": [import_site(edge.reference) for edge in source.path],
                                       "source_direct_impact": source.source_direct_impact} for source in finding.sources]}
                for finding in run.indirect]
    evidences, explanations = [], []
    builder = ImportEvidenceBuilder(run.index.scanner.project_path, run.inventory)
    for finding in (*run.direct, *run.indirect):
        try:
            evidence = builder.build(finding)
        except Exception:
            evidence = ImportEvidence(finding.finding_id, finding.impact_type, finding.target_module_id, None,
                                      None, None, None, "evidence_unavailable", "源码证据构建失败，需人工核查。", (),
                                      "unavailable", ({"code": "evidence_unavailable", "message": "源码证据暂不可用。"},))
        evidences.append(evidence.to_dict())
        try:
            explanation = explain_module_evidence(evidence, run=run, finding=finding).to_dict()
        except Exception:
            explanation = None
        explanations.append({"evidence_reference": evidence.evidence_reference, "provider": "rule",
                             "status": "available" if explanation else "unavailable", "explanation": explanation})
    assessments = [{"reference_id": item.before.reference_id, "before": reference_data(item.before),
                    "after": reference_data(item.after), "effect": item.effect, "reason": item.reason} for item in run.assessments]
    return {"report_kind": "module_impact", "schema_version": 1, "change_domain": "module",
            "change": run.change_spec.to_dict(), "validation": {"valid": True, "diagnostics": []},
            "summary": {"direct_import_count": len(direct), "indirect_1hop_module_count": sum(item.hop == 1 for item in run.indirect),
                        "indirect_2hop_module_count": sum(item.hop == 2 for item in run.indirect),
                        "manual_review_count": len(diagnostics["manual_review_imports"]) + len(diagnostics["import_diagnostics"]),
                        "unresolved_import_count": len(diagnostics["unresolved_imports"])},
            "counting_units": {"direct": "import_reference", "indirect": "unique_upstream_module"},
            "coverage": module_coverage(run.index, run.inventory, references), "diagnostics": diagnostics,
            "import_assessments": assessments, "import_impacts": direct, "module_indirect_impacts": indirect,
            "evidences": evidences, "explanations": explanations}


def render_module_report(report):
    change = report["change"]
    target = change["target_module_id"]
    after = change["after"]
    plan = f"{target} → {after['module_id']}" if after else f"删除 {target}（仅拟定）"
    summary = report["summary"]
    lines = [f"OpenImpact 模块变更：{plan}", "分析不修改源码。Direct 为项目内静态导入断裂；Indirect 仅建议检查。",
             f"Direct={summary['direct_import_count']} / 1-hop={summary['indirect_1hop_module_count']} / 2-hop={summary['indirect_2hop_module_count']}",
             f"Coverage={report['coverage']['status']}：{report['coverage']['message']}"]
    for evidence in report["evidences"]:
        location = evidence["location"] or {}
        lines.append(f"{evidence['impact_type']} {location.get('file', 'unavailable')}:{location.get('line', '?')}：{evidence['reason']}")
        for path in evidence["propagation_path"]:
            lines.append(" → ".join(path["modules"]))
        if evidence["source_snippet"]:
            lines.append(evidence["source_snippet"])
    lines.append(f"人工检查={summary['manual_review_count']}；未解析导入={summary['unresolved_import_count']}")
    return "\n".join(lines)
