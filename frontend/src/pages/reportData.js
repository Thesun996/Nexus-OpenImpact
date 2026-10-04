// Core preserves one Evidence slot per definite finding: Direct, then Indirect.
// Verify identity before showing source; missing/reordered slots stay unavailable.
export function correspondingEvidence(report, index, finding) {
  const evidence = report.evidences?.[index]
  if (!evidence || evidence.impact_type !== finding.impact_type) return null
  if (finding.impact_type === 'direct') {
    if (evidence.target_symbol !== finding.target_symbol_id
      || evidence.location?.file !== finding.file
      || evidence.location?.line !== finding.line
      || evidence.location?.column !== finding.column) return null
  } else {
    if (evidence.target_symbol !== report.change?.target_symbol_id) return null
    if (evidence.status === 'available' && !evidence.propagation_path?.some((path) => path.symbols?.[0] === finding.impacted_symbol_id)) return null
  }
  return evidence
}

export function correspondingExplanation(report, index, evidence) {
  const record = report.explanations?.[index]
  if (!record || !evidence) return null
  const linked = record.evidence
  if (linked?.target_symbol !== evidence.target_symbol
    || linked?.impact_type !== evidence.impact_type
    || linked?.location?.file !== evidence.location?.file
    || linked?.location?.line !== evidence.location?.line
    || linked?.location?.column !== evidence.location?.column) return null
  return record
}
