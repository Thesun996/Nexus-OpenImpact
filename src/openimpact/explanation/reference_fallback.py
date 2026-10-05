"""Check order for existing module/symbol evidence; no reference resolution."""

from openimpact.explanation.models import ExplanationResult
from openimpact.reporting.source_reader import read_source_snapshot


def explain_reference_evidence(evidence, change, terminal, terminal_reason, root, expected_hash):
    if evidence['status'] != 'available' or evidence.get('source_snippet') is None:
        raise ValueError('源码证据不可用，不能生成对应解释。')
    domain = change['change_domain']
    target = change.get('target_module_id') if domain == 'module' else change.get('target_symbol_id')
    after = change['after']
    new_name = (after['module_id'] if domain == 'module' else after['name']) if after else None
    description = f'{target} → {new_name}' if new_name else f'拟删除 {target}'
    location = terminal['location']
    site = f"{location['file']}:{location['line']}:{location['column']}"
    expression = terminal.get('expression') or terminal.get('import_expression')
    verified = False
    try:
        _, snippet, _, errors = read_source_snapshot(root, location['file'], location['line'],
            location['column'], location.get('end_line', location['line']), expected_hash)
        verified = not errors and snippet is not None and isinstance(expression, str) and expression in snippet
    except (OSError, ValueError, UnicodeError):
        pass
    paths = evidence.get('propagation_path', ())
    representative = min(paths, key=lambda path: (len(path['modules']), path['source_direct_impact'])) if paths else None
    indirect = evidence['impact_type'].startswith('indirect_')
    current = evidence['location']
    current_site = f"{current['file']}:{current['line']}"
    summary = (f'{current_site} 位于 {target} 的上游静态依赖路径，建议检查。' if indirect
               else f'{current_site} 的项目内引用因拟定变更发生静态断裂。')
    why = f'变更：{description}。\n判断依据：{evidence["reason"]}'
    if indirect:
        why += f'\n确定断裂的原始引用位于 {site}：{terminal_reason}'
    if representative:
        why += '\n代表路径：' + ' → '.join(representative['modules']) + '。静态路径不保证运行时失败。'
    checks = [f'1. 先核对 {site}：{expression[:800] if verified else "源码未能复核，请手动打开原文件"}。'
              '此处原来绑定项目内目标，拟定变更后旧目标不再提供；分析没有改动文件。']
    if domain == 'module':
        checks.append('2. 人工确认旧模块入口是否还需要兼容，以及导入别名下的现有使用点是否仍指向计划保留的接口；'
                      '当前证据没有证明所有使用点或运行时导入结果。')
    else:
        checks.append('2. 对照原变量定义与该读取位置，检查新名称或删除计划是否保持调用方需要的业务含义；'
                      '当前分析没有评估变量取值变化的后果。')
    if indirect and representative:
        # Path is supplied by the report, not reconstructed by string matching.
        upstream_sites = representative['import_sites']
        if domain == 'module':
            upstream_sites = upstream_sites[:-1]  # final import is the direct seed
        for import_location in reversed(upstream_sites[:2]):
            upstream = f"{import_location['file']}:{import_location['line']}:{import_location['column']}"
            checks.append(f'{len(checks) + 1}. 再核对上游导入 {upstream}：这层是否依赖受影响模块的接口？'
                          '该位置只表示静态上游依赖，没有判定其运行时一定失败。')
    checks.append(f'{len(checks) + 1}. 检查现有测试是否覆盖原引用及上游入口；测试文件、执行结果和动态引用需人工确认。')
    if len(paths) > 1:
        checks.append(f'本记录保留 {len(paths)} 条来源路径，以上仅展开一条代表路径；其余请查看证据。')
    return ExplanationResult(summary, why, 'unknown', '\n'.join(checks), 1.0)
