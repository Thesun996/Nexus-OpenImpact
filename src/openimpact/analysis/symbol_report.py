"""Independent symbol report contract; source evidence uses frozen safe readers."""

from dataclasses import asdict
from openimpact.analysis.symbol_references import resolve_symbol_references, resolve_symbol_imports
from openimpact.analysis.module_report import reference_data
from openimpact.reporting.source_reader import read_source_snapshot
from openimpact.reporting.import_evidence import import_site
from openimpact.explanation.models import ExplanationResult


def symbol_diagnostics(index, inventory, references):
    imports = tuple(ref for ref in resolve_symbol_imports(index, inventory) if ref.syntax.import_type == 'import')
    return {
        'parse_errors': [{'file': file.as_posix(), 'line': item.lineno, 'column': item.col_offset, 'kind': item.kind,
                          'message': item.message if item.kind == 'syntax_error' else '项目源码无法读取或解码。'}
                         for file, items in sorted(index.parse_diagnostics.items()) for item in items],
        'unsupported_modules': [asdict(item) for item in inventory.modules.modules if not item.selectable],
        'unsupported_symbols': [asdict(item) for item in inventory.symbols if not item.selectable],
        'syntax_diagnostics': [{'file': file.as_posix(), 'code': code, 'line': line, 'column': column}
                               for file, parsed in sorted(index.parsed_files.items()) for code, line, column in parsed.symbol_diagnostics],
        'import_syntax_diagnostics': [{'file': file.as_posix(), **asdict(item)} for file, parsed in sorted(index.parsed_files.items()) for item in parsed.module_diagnostics],
        'manual_review_imports': [reference_data(ref) for ref in imports if ref.status == 'manual_review'],
        'unresolved_imports': [reference_data(ref) for ref in imports if ref.status == 'unresolved'],
        'manual_review_references': [ref.to_dict() for ref in references if ref.status == 'manual_review'],
        'unresolved_references': [ref.to_dict() for ref in references if ref.status == 'unresolved'],
    }


def symbol_coverage(index, inventory, references):
    partial = any(symbol_diagnostics(index, inventory, references).values())
    return {'status': 'partial' if partial else 'complete', 'analysis_scope': 'project_root_static_symbols',
            'python_files': len(inventory.modules.modules), 'supported_symbols': sum(item.selectable for item in inventory.symbols),
            'message': '覆盖不完整；零影响不证明项目没有其他影响。' if partial else '已覆盖受支持根模块的明确静态变量引用；不模拟运行时与动态反射。'}


def symbol_inspect(index, inventory):
    references = resolve_symbol_references(index, inventory)
    return {'symbol_inventory': inventory.to_dict(), 'symbol_coverage': symbol_coverage(index, inventory, references),
            'symbol_diagnostics': symbol_diagnostics(index, inventory, references)}


def propagation_data(source, direct_by_id):
    terminal = direct_by_id[source.source_direct_impact].assessment.before
    modules = [source.path[0].importer_module_id, *(edge.target_module_id for edge in source.path)]
    return {'modules': modules, 'import_sites': [import_site(edge.reference) for edge in source.path],
            'source_direct_impact': source.source_direct_impact, 'terminal_reference': terminal.to_dict()}


def build_symbol_report(run):
    refs = tuple(item.before for item in run.assessments)
    diagnostics = symbol_diagnostics(run.index, run.inventory, refs)
    direct_by_id = {item.finding_id: item for item in run.direct}
    direct = [{'finding_id': item.finding_id, 'impact_type': item.impact_type,
               'target_symbol_id': run.change_spec.target_symbol_id, 'impacted_module_id': item.assessment.before.source_module,
               'reference_id': item.assessment.before.reference_id, 'location': item.assessment.before.to_dict()['location'],
               'before_resolution': item.assessment.before.to_dict(), 'after_resolution': item.assessment.after.to_dict(),
               'certainty': 'definite_project_reference_break', 'rule': item.rule, 'reason': item.assessment.reason} for item in run.direct]
    indirect = [{'finding_id': item.finding_id, 'impact_type': item.impact_type, 'impacted_module_id': item.impacted_module_id,
                 'target_symbol_id': run.change_spec.target_symbol_id, 'hop': item.hop, 'certainty': 'needs_review',
                 'reason': item.reason, 'source_direct_impacts': [source.source_direct_impact for source in item.sources],
                 'propagation_path': [propagation_data(source, direct_by_id) for source in item.sources]} for item in run.indirect]
    evidences, explanations = [], []
    for finding in (*direct, *indirect):
        paths = finding.get('propagation_path', [])
        if paths:
            representative = min(paths, key=lambda path: (len(path['modules']), path['source_direct_impact']))
            site = representative['import_sites'][0]
        else: site = finding['location']
        module = next((item for item in run.inventory.modules.modules if item.file == site['file']), None)
        try:
            location, snippet, digest, errors = read_source_snapshot(run.index.scanner.project_path, site['file'], site['line'], site['column'], site.get('end_line', site['line']), module.source_hash if module else None)
            evidence_errors = [asdict(error) for error in errors]
        except Exception:
            snippet, digest, evidence_errors = None, None, [{'code': 'evidence_unavailable', 'message': '源码证据暂不可用。'}]
        evidence = {'evidence_reference': finding['finding_id'], 'impact_type': finding['impact_type'],
                    'target_symbol_id': run.change_spec.target_symbol_id, 'location': site, 'source_snippet': snippet,
                    'source_hash': digest, 'rule': finding.get('rule', 'upstream_symbol_dependency_review'), 'reason': finding['reason'],
                    'propagation_path': paths, 'reference_expression': finding.get('before_resolution', {}).get('expression'),
                    'before_resolution': finding.get('before_resolution'), 'after_resolution': finding.get('after_resolution'),
                    'status': 'available' if snippet is not None else 'unavailable', 'diagnostics': evidence_errors}
        evidences.append(evidence)
        try:
            result = ExplanationResult(summary=f"{site['file']}:{site['line']} 的静态符号引用需要检查。", why_affected=finding['reason'],
                                       risk_level='unknown', suggested_check='对照原定义、引用和依赖路径检查拟定变更；分析不会修改文件。', confidence=1.0).to_dict()
        except Exception: result = None
        explanations.append({'evidence_reference': finding['finding_id'], 'provider': 'rule', 'status': 'available' if result else 'unavailable', 'explanation': result})
    return {'change_domain': 'symbol', 'report_kind': 'symbol_impact', 'schema_version': 1, 'change': run.change_spec.to_dict(),
            'validation': {'valid': True, 'diagnostics': []},
            'summary': {'direct_reference_count': len(direct), 'indirect_1hop_module_count': sum(item.hop == 1 for item in run.indirect),
                        'indirect_2hop_module_count': sum(item.hop == 2 for item in run.indirect),
                        'manual_review_count': len(diagnostics['manual_review_references']) + len(diagnostics['syntax_diagnostics']) + len(diagnostics['import_syntax_diagnostics']) + len(diagnostics['manual_review_imports']),
                        'unresolved_reference_count': len(diagnostics['unresolved_references']) + len(diagnostics['unresolved_imports'])},
            'counting_units': {'direct': 'unique_source_reference', 'indirect': 'unique_upstream_module'},
            'coverage': symbol_coverage(run.index, run.inventory, refs), 'diagnostics': diagnostics,
            'reference_assessments': [{'reference_id': item.before.reference_id, 'before': item.before.to_dict(), 'after': item.after.to_dict(), 'effect': item.effect, 'reason': item.reason} for item in run.assessments],
            'reference_impacts': direct, 'symbol_indirect_impacts': indirect, 'evidences': evidences, 'explanations': explanations}


def render_symbol_report(report):
    summary = report['summary']
    return '\n'.join([f"OpenImpact 符号变更：{report['change']['target_symbol_id']} / {report['change']['change_type']}",
                       f"Direct={summary['direct_reference_count']} / 1-hop={summary['indirect_1hop_module_count']} / 2-hop={summary['indirect_2hop_module_count']}",
                       f"Coverage={report['coverage']['status']}：{report['coverage']['message']}",
                       *[f"{item['location']['file']}:{item['location']['line']} {item['reason']}" for item in report['evidences']]])
