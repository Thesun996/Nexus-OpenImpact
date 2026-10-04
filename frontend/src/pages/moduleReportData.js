// Independent report namespace; never reinterpret function findings as imports.
export function moduleFindings(report) {
  return [...(report.import_impacts || []), ...(report.module_indirect_impacts || [])]
}

export const moduleImpactLabel = type => ({ direct_import: '直接导入影响', indirect_1hop: '1 层上游模块', indirect_2hop: '2 层上游模块' }[type] || type)

function sameSite(left, right) {
  return !!left && !!right && ['file', 'line', 'column', 'reference_id'].every(key => left[key] === right[key])
}

export function moduleEvidence(report, index, finding) {
  const evidence = report.evidences?.[index]
  if (!evidence || evidence.evidence_reference !== finding.finding_id || evidence.impact_type !== finding.impact_type
    || evidence.target_module_id !== finding.target_module_id) return null
  // Safe unavailable records remain associated, but never lend another snippet.
  if (evidence.status !== 'available') return evidence
  if (!Array.isArray(evidence.propagation_path) || !evidence.propagation_path.length) return null
  const directIds = new Set((report.import_impacts || []).map(item => item.finding_id))
  for (const path of evidence.propagation_path) {
    if (!Array.isArray(path.modules) || !Array.isArray(path.import_sites) || path.modules.length !== path.import_sites.length + 1
      || path.modules[0] !== finding.impacted_module_id || path.modules.at(-1) !== finding.target_module_id
      || !directIds.has(path.source_direct_impact)) return null
    const seed = report.import_impacts.find(item => item.finding_id === path.source_direct_impact)
    if (!sameSite(path.import_sites.at(-1), seed.location)) return null
  }
  if (finding.impact_type === 'direct_import') {
    if (!sameSite(evidence.location, finding.location) || evidence.propagation_path.some(path => path.modules.length !== 2) || evidence.propagation_path.some(path => path.source_direct_impact !== finding.finding_id)) return null
  } else if (JSON.stringify(evidence.propagation_path) !== JSON.stringify(finding.propagation_path)
    || !sameSite(evidence.location, evidence.propagation_path[0].import_sites[0])) return null
  return evidence
}

export function moduleExplanation(report, index, evidence) {
  const record = report.explanations?.[index]
  return evidence?.status === 'available' && record?.evidence_reference === evidence.evidence_reference && record.status === 'available' ? record : null
}

const moduleReasonLabels = {
  relative_import_unsupported: '相对导入超出首版根模块范围，需人工检查',
  conditional_or_local_import_unsupported: '条件或局部导入的执行环境未确定，需人工检查',
  package_import_unsupported: '复杂包导入暂不能可靠解析',
  wildcard_import_unsupported: '通配导入未做符号绑定，需人工检查',
  imported_member_not_proven: '无法确认导入成员，可能涉及重导出或重绑定',
  module_not_in_project: '未确认项目内目标，未纳入确定依赖图',
  unsupported_importer: '导入来源超出首版支持范围',
}
export function moduleDiagnosticEntries(diagnostics) {
  return Object.fromEntries(Object.entries(diagnostics || {}).map(([category, items]) => [category,
    Array.isArray(items) ? items.map(item => item?.location ? { ...item, ...item.location,
      message: `${moduleReasonLabels[item.reason] || item.reason || item.message || ''}${item.import_expression ? ` · ${item.import_expression}` : ''}` } : item) : items]))
}
