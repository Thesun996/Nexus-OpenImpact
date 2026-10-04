import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { correspondingEvidence, correspondingExplanation } from '../src/pages/reportData.js'

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
