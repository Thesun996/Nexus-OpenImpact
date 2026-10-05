export const symbolFindings = report => [...(report.reference_impacts || []), ...(report.symbol_indirect_impacts || [])]
export const symbolImpactLabel = type => ({ direct_symbol_reference: '直接符号引用影响', indirect_1hop: '1 层上游模块', indirect_2hop: '2 层上游模块' }[type] || type)
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)
const sameSite = (a, b) => a && b && ['file','line','column','end_line','end_column'].every(key => a[key] === b[key])
export function symbolEvidence(report, index, finding) {
  const evidence = report.evidences?.[index]
  if (!evidence || evidence.evidence_reference !== finding.finding_id || evidence.impact_type !== finding.impact_type
    || evidence.target_symbol_id !== finding.target_symbol_id) return null
  if (evidence.status !== 'available') return evidence
  if (finding.impact_type === 'direct_symbol_reference') {
    return sameSite(evidence.location, finding.location) && same(evidence.before_resolution, finding.before_resolution)
      && same(evidence.after_resolution, finding.after_resolution) && evidence.reference_expression === finding.before_resolution.expression
      && evidence.propagation_path?.length === 0 ? evidence : null
  }
  if (!same(evidence.propagation_path, finding.propagation_path) || !evidence.propagation_path?.length) return null
  for (const path of evidence.propagation_path) {
    const seed = report.reference_impacts?.find(item => item.finding_id === path.source_direct_impact)
    if (!seed || !Array.isArray(path.modules) || !Array.isArray(path.import_sites)
      || path.modules.length !== path.import_sites.length + 1 || path.modules[0] !== finding.impacted_module_id
      || path.modules.at(-1) !== seed.impacted_module_id || !same(path.terminal_reference, seed.before_resolution)) return null
  }
  return evidence.propagation_path.some(path => sameSite(evidence.location, path.import_sites[0])) ? evidence : null
}
export function symbolExplanation(report, index, evidence) {
  const record = report.explanations?.[index]
  return evidence?.status === 'available' && record?.evidence_reference === evidence.evidence_reference && record.status === 'available' ? record : null
}
export const symbolDiagnosticEntries = diagnostics => Object.fromEntries(Object.entries(diagnostics || {}).map(([category, items]) => [category,
  Array.isArray(items) ? items.map(item => ({ ...item, ...item.location, message: item.message || item.reason || item.code || '需要检查静态分析边界' })) : items]))
export const SYMBOL_REASONS = {
  private_symbol_unsupported: '首版仅分析公开变量和常量；私有名称暂不可选。',
  symbol_rebound: '存在重复定义或全局写入，无法证明唯一绑定。',
  conditional_definition_unsupported: '定义位于条件或异常处理环境中，需要人工检查。',
  complex_definition_unsupported: '当前只支持唯一简单字面量赋值或带值注解赋值。',
  dynamic_definition_unsupported: '动态命名空间写入使定义无法确定。',
  dynamic_exports_unsupported: '动态导出超出首版范围。',
  unsupported_module_layout: '包与嵌套模块超出首版范围。',
}
