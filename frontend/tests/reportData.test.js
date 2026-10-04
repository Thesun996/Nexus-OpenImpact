import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  correspondingEvidence, correspondingExplanation, isUsableExplanation,
  reportFindings, reportIntegrityDiagnostics,
} from '../src/pages/reportData.js'

const report = JSON.parse(readFileSync(new URL('../src/demo/fixtures/analyze.json', import.meta.url), 'utf8'))

test('all saved Direct/Indirect records map to their actual evidence and explanation', () => {
  const findings = [...report.direct_impacts, ...report.indirect_impacts]
  findings.forEach((finding, index) => {
    const evidence = correspondingEvidence(report, index, finding)
    assert.equal(evidence, report.evidences[index])
    assert.equal(correspondingExplanation(report, index, evidence), report.explanations[index])
  })
})

test('same-line calls with a different column do not share Direct evidence', () => {
  const finding = { ...report.direct_impacts[0], column: report.direct_impacts[0].column + 1 }
  assert.equal(correspondingEvidence(report, 0, finding), null)
})

test('missing evidence/explanation slots remain unavailable, without filling demo data', () => {
  assert.equal(correspondingEvidence({ ...report, evidences: [] }, 0, report.direct_impacts[0]), null)
  assert.equal(correspondingExplanation({ ...report, explanations: [] }, 0, report.evidences[0]), null)
  assert.equal(correspondingExplanation(report, 0, null), null)
})

test('different upstream Symbol or unrelated explanation is rejected', () => {
  assert.equal(correspondingEvidence(report, 1, { ...report.indirect_impacts[0], impacted_symbol_id: 'other.f' }), null)
  assert.equal(correspondingExplanation(report, 1, report.evidences[2]), null)
})

test('same leading Indirect Symbol is insufficient when the remaining path or call site differs', () => {
  const changedPath = structuredClone(report)
  changedPath.evidences[1].propagation_path[0].symbols[1] = 'other.report'
  assert.equal(correspondingEvidence(changedPath, 1, changedPath.indirect_impacts[0]), null)
  const changedSite = structuredClone(report)
  changedSite.evidences[1].propagation_path[0].call_sites[1].column += 1
  assert.equal(correspondingEvidence(changedSite, 1, changedSite.indirect_impacts[0]), null)
  const changedLocation = structuredClone(report)
  changedLocation.evidences[1].location.file = 'other.py'
  assert.equal(correspondingEvidence(changedLocation, 1, changedLocation.indirect_impacts[0]), null)
})

test('Indirect path must retain the actual Direct reference and all source paths', () => {
  const changedReference = structuredClone(report)
  changedReference.evidences[2].propagation_path[0].direct_evidence_reference = 'call:other.py:5:11'
  assert.equal(correspondingEvidence(changedReference, 2, changedReference.indirect_impacts[1]), null)
  const omittedSource = structuredClone(report)
  omittedSource.indirect_impacts[0].sources.push(structuredClone(omittedSource.indirect_impacts[0].sources[0]))
  assert.equal(correspondingEvidence(omittedSource, 1, omittedSource.indirect_impacts[0]), null)
})

test('Direct unavailable Core placeholder retains its diagnostic at the same index', () => {
  const failed = structuredClone(report)
  failed.evidences[0] = {
    ...failed.evidences[0], location: null, source_snippet: null, source_hash: null,
    call_expression: null, status: 'unavailable',
    diagnostics: [{ code: 'evidence_unavailable', message: '证据生成失败，影响分析结果仍可查看。' }],
  }
  failed.explanations[0] = {
    evidence: structuredClone(failed.evidences[0]), explanation: null,
    diagnostics: [{ code: 'evidence_unavailable', message: '源码证据不可用，无法生成解释。' }],
  }
  assert.equal(correspondingEvidence(failed, 0, failed.direct_impacts[0]), failed.evidences[0])
  assert.equal(correspondingExplanation(failed, 0, failed.evidences[0]), failed.explanations[0])
  assert.equal(failed.explanations[0].explanation, null)
  assert.deepEqual(reportIntegrityDiagnostics(failed), [])
})

test('Indirect unavailable placeholder can lack location/path but cannot contradict retained identity', () => {
  const failed = structuredClone(report)
  failed.evidences[1] = {
    ...failed.evidences[1], location: null, propagation_path: [],
    source_snippet: null, source_hash: null, call_expression: null, status: 'unavailable',
    diagnostics: [{ code: 'evidence_unavailable', message: '证据生成失败。' }],
  }
  assert.equal(correspondingEvidence(failed, 1, failed.indirect_impacts[0]), failed.evidences[1])
  failed.evidences[1].evidence_reference = 'call:other.py:5:11'
  assert.equal(correspondingEvidence(failed, 1, failed.indirect_impacts[0]), null)
})

test('unavailable status cannot excuse a conflicting file, column, or target', () => {
  for (const changes of [{ location: { file: 'other.py', line: 5, column: 11 } }, { target_symbol: 'other.format_date' }]) {
    const failed = structuredClone(report)
    failed.evidences[0] = { ...failed.evidences[0], ...changes, status: 'unavailable', source_snippet: null }
    assert.equal(correspondingEvidence(failed, 0, failed.direct_impacts[0]), null)
  }
})

test('explanation requires the complete evidence snapshot, including source, hash, path and status', () => {
  for (const [field, value] of [
    ['source_snippet', 'return unrelated()'], ['source_hash', 'different-source-snapshot'],
    ['propagation_path', []], ['status', 'unavailable'],
  ]) {
    const changed = structuredClone(report)
    changed.explanations[1].evidence[field] = value
    assert.equal(correspondingExplanation(changed, 1, changed.evidences[1]), null, field)
  }
})

test('evidence content equality does not depend on JSON object key order', () => {
  const reordered = structuredClone(report)
  reordered.explanations[0].evidence = Object.fromEntries(Object.entries(reordered.evidences[0]).reverse())
  reordered.explanations[0].evidence.location = Object.fromEntries(Object.entries(reordered.evidences[0].location).reverse())
  assert.equal(correspondingExplanation(reordered, 0, reordered.evidences[0]), reordered.explanations[0])
})

test('null explanation remains a corresponding record so its diagnostic can be displayed', () => {
  const failed = structuredClone(report)
  failed.explanations[0].explanation = null
  failed.explanations[0].diagnostics = [{ code: 'explanation_unavailable', message: '解释生成失败。' }]
  assert.equal(correspondingExplanation(failed, 0, failed.evidences[0]), failed.explanations[0])
  assert.equal(isUsableExplanation(failed.explanations[0].explanation), false)
})

test('manual review and unresolved calls do not consume slots or generate definite impacts', () => {
  const uncertain = structuredClone(report)
  uncertain.direct_impacts = []
  uncertain.indirect_impacts = []
  uncertain.evidences = []
  uncertain.explanations = []
  uncertain.manual_reviews = [{
    ...report.direct_impacts[0], effect: 'manual_review', after_status: 'manual_review',
    reason: '存在 *args 展开，静态证据不足。',
  }]
  uncertain.diagnostics.unresolved_calls = [{ file: 'other.py', line: 3, column: 4, expression: 'external.fn()', reason: 'external_module' }]
  uncertain.coverage.status = 'partial'
  uncertain.summary = { direct_impact_count: 0, indirect_1hop_count: 0, indirect_2hop_count: 0, manual_review_count: 1, pre_existing_problem_count: 0, unresolved_call_count: 1 }
  assert.deepEqual(reportFindings(uncertain), [])
  assert.deepEqual(reportIntegrityDiagnostics(uncertain), [])
  assert.equal(correspondingEvidence(uncertain, 0, uncertain.manual_reviews[0]), null)
})

test('partial coverage retains confirmed findings and their same-order evidence', () => {
  const partial = { ...report, coverage: { ...report.coverage, status: 'partial' } }
  assert.equal(reportFindings(partial).length, 3)
  assert.equal(correspondingEvidence(partial, 1, partial.indirect_impacts[0]), partial.evidences[1])
})

test('zero-impact report stays empty; integrity diagnostics never repair or invent statistics', () => {
  const empty = { ...report, direct_impacts: [], indirect_impacts: [], evidences: [], explanations: [], summary: { ...report.summary, direct_impact_count: 0, indirect_1hop_count: 0, indirect_2hop_count: 0 } }
  assert.deepEqual(reportFindings(empty), [])
  assert.deepEqual(reportIntegrityDiagnostics(empty), [])
  const inconsistent = { ...empty, summary: { ...empty.summary, direct_impact_count: 1 } }
  assert.equal(reportIntegrityDiagnostics(inconsistent)[0].code, 'report_count_mismatch')
  assert.equal(inconsistent.summary.direct_impact_count, 1)
  assert.deepEqual(reportFindings(inconsistent), [])
})

test('missing or reordered slots create clear integrity diagnostics without looking elsewhere', () => {
  const swapped = structuredClone(report)
  ;[swapped.evidences[1], swapped.evidences[2]] = [swapped.evidences[2], swapped.evidences[1]]
  assert.equal(correspondingEvidence(swapped, 1, swapped.indirect_impacts[0]), null)
  assert.equal(reportIntegrityDiagnostics(swapped).filter((diagnostic) => diagnostic.code === 'report_evidence_mismatch').length, 2)
  const missing = { ...report, explanations: [] }
  assert.ok(reportIntegrityDiagnostics(missing).some((diagnostic) => diagnostic.code === 'report_evidence_slots_mismatch'))
  assert.equal(reportIntegrityDiagnostics(missing).filter((diagnostic) => diagnostic.code === 'report_explanation_mismatch').length, 3)
})

test('explanation display guard accepts only valid fields and finite contract confidence', () => {
  const explanation = report.explanations[0].explanation
  assert.equal(isUsableExplanation(explanation), true)
  for (const value of [null, {}, { ...explanation, summary: '' }, { ...explanation, why_affected: {} }, { ...explanation, risk_level: 'certain' }, { ...explanation, confidence: NaN }, { ...explanation, confidence: true }, { ...explanation, confidence: 1.1 }]) {
    assert.equal(isUsableExplanation(value), false)
  }
})

test('absent report and arrays are safe and never substituted with Demo data', () => {
  assert.deepEqual(reportFindings(null), [])
  assert.deepEqual(reportIntegrityDiagnostics(null), [])
  assert.equal(correspondingEvidence(null, 0, null), null)
  assert.equal(correspondingExplanation(null, 0, null), null)
})
