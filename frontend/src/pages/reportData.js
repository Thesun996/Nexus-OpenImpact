const list = (value) => Array.isArray(value) ? value : []

// Core preserves one slot per definite finding: Direct, then Indirect.
// Manual review and pre-existing problems have no Evidence slots.
export function reportFindings(report) {
  return [...list(report?.direct_impacts), ...list(report?.indirect_impacts)]
}

function sameLocation(left, right) {
  return !!left && !!right && left.file === right.file
    && left.line === right.line && left.column === right.column
}

function equalJson(left, right) {
  if (left === right) return true
  if (left == null || right == null || typeof left !== 'object' || typeof right !== 'object') return false
  if (Array.isArray(left) !== Array.isArray(right)) return false
  const keys = Object.keys(left)
  return keys.length === Object.keys(right).length
    && keys.every((key) => Object.hasOwn(right, key) && equalJson(left[key], right[key]))
}

function callReference(call) {
  return call?.file != null && call.line != null && call.column != null
    ? `call:${call.file}:${call.line}:${call.column}` : null
}

function matchingPath(path, source) {
  const edges = list(source?.propagation_path)
  const symbols = edges.length ? [edges[0].caller_symbol_id, ...edges.map((edge) => edge.callee_symbol_id)] : []
  return edges.length > 0 && equalJson(path?.symbols, symbols)
    && list(path?.call_sites).length === edges.length
    && edges.every((edge, index) => sameLocation(path.call_sites[index], edge))
    && (path.direct_evidence_reference == null || path.direct_evidence_reference === callReference(source.direct_call))
}

// Never search another index to fill a missing slot. Retain unavailable placeholders
// (including Core's location=null/path=[] failure shape), but reject contradictory
// identity metadata. A placeholder without identity has no source to display.
export function correspondingEvidence(report, index, finding) {
  const evidence = list(report?.evidences)[index]
  if (!finding || !evidence || evidence.impact_type !== finding.impact_type
    || !['available', 'unavailable'].includes(evidence.status)) return null
  const unavailable = evidence.status === 'unavailable'
  if (finding.impact_type === 'direct') {
    if (evidence.target_symbol !== finding.target_symbol_id
      || (evidence.location == null ? !unavailable : !sameLocation(evidence.location, finding))
      || (evidence.evidence_reference != null && evidence.evidence_reference !== callReference(finding))
      || list(evidence.propagation_path).length !== 0) return null
  } else if (['indirect_1hop', 'indirect_2hop'].includes(finding.impact_type)) {
    const sources = list(finding.sources)
    const paths = list(evidence.propagation_path)
    const representative = sources.reduce((shortest, source) =>
      !shortest || list(source.propagation_path).length < list(shortest.propagation_path).length ? source : shortest, null)
    const firstEdge = representative?.propagation_path?.[0]
    if (evidence.target_symbol !== report?.change?.target_symbol_id
      || sources.some((source) => source.propagation_path?.[0]?.caller_symbol_id !== finding.impacted_symbol_id)
      || (evidence.location == null ? !unavailable : !sameLocation(evidence.location, firstEdge))
      || (evidence.evidence_reference != null && evidence.evidence_reference !== callReference(representative?.direct_call))) return null
    if ((!unavailable || paths.length > 0)
      && (paths.length !== sources.length || !paths.every((path, pathIndex) => matchingPath(path, sources[pathIndex])))) return null
  } else return null
  return evidence
}

export function correspondingExplanation(report, index, evidence) {
  const record = list(report?.explanations)[index]
  // Location alone cannot identify a source snapshot or an Indirect path.
  return record && evidence && equalJson(record.evidence, evidence) ? record : null
}

export function isUsableExplanation(explanation) {
  return !!explanation && ['summary', 'why_affected', 'suggested_check'].every((field) =>
    typeof explanation[field] === 'string' && explanation[field].trim().length > 0)
    && ['low', 'medium', 'high', 'unknown'].includes(explanation.risk_level)
    && typeof explanation.confidence === 'number' && Number.isFinite(explanation.confidence)
    && explanation.confidence >= 0 && explanation.confidence <= 1
}

// These are display-integrity diagnostics only; do not recalculate Core's summary
// or invent missing findings when a report violates its public data contract.
export function reportIntegrityDiagnostics(report) {
  if (!report) return []
  const findings = reportFindings(report)
  const counts = {
    direct_impact_count: list(report.direct_impacts).length,
    indirect_1hop_count: list(report.indirect_impacts).filter((finding) => finding.impact_type === 'indirect_1hop').length,
    indirect_2hop_count: list(report.indirect_impacts).filter((finding) => finding.impact_type === 'indirect_2hop').length,
    manual_review_count: list(report.manual_reviews).length,
    pre_existing_problem_count: list(report.pre_existing_problems).length,
    unresolved_call_count: list(report.diagnostics?.unresolved_calls).length,
  }
  const diagnostics = Object.entries(counts).flatMap(([field, count]) =>
    report.summary?.[field] === count ? [] : [{ code: 'report_count_mismatch', message: `${field} 的报告计数与对应记录数不一致，请核查响应；页面保留原始数据。` }])
  if (list(report.evidences).length !== findings.length || list(report.explanations).length !== list(report.evidences).length) {
    diagnostics.push({ code: 'report_evidence_slots_mismatch', message: '影响、Evidence 与 Explanation 的同序记录数量不一致，缺失项保持不可用。' })
  }
  findings.forEach((finding, index) => {
    const evidence = correspondingEvidence(report, index, finding)
    if (!evidence) diagnostics.push({ code: 'report_evidence_mismatch', message: `第 ${index + 1} 条影响缺少可对应的 Evidence；未使用其他记录填充。` })
    else if (!correspondingExplanation(report, index, evidence)) diagnostics.push({ code: 'report_explanation_mismatch', message: `第 ${index + 1} 条 Evidence 缺少可对应的 Explanation；源码证据和静态影响仍可查看。` })
  })
  return diagnostics
}
