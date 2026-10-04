import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createInitialState, workflowReducer, buildChangePayload } from '../src/state/workflow.js'
import { createWorkflowActions } from '../src/state/actions.js'
import { createModuleDraft, updateModuleDraft, buildModulePayload } from '../src/state/moduleDraft.js'
import { moduleFindings, moduleEvidence, moduleExplanation } from '../src/pages/moduleReportData.js'
const fixture = JSON.parse(readFileSync(new URL('./fixtures/module-responses.json', import.meta.url)))
const original = new File(['actual bytes'], 'actual.zip')
function harness(overrides = {}) {
  let state = createInitialState()
  const calls = []
  const client = {
    inspect: async (...args) => { calls.push(['inspect', ...args]); return structuredClone(fixture.inspect) },
    validate: async (...args) => { calls.push(['validate', ...args]); return structuredClone(fixture.validation) },
    analyze: async (...args) => { calls.push(['analyze', ...args]); return structuredClone(fixture.report) },
    ...overrides,
  }
  const actions = createWorkflowActions({ getState: () => state, dispatch: a => { state = workflowReducer(state, a) }, client })
  return { actions, calls, state: () => state }
}
async function ready(h) {
  h.actions.selectFile(original); assert.equal(await h.actions.inspectProject(), true)
  h.actions.selectDomain('module'); h.actions.selectModule('utils'); h.actions.updateChange({ newModuleName: 'formatting' })
}
test('module draft types have precise isolated payloads without fake signatures', () => {
  let change = updateModuleDraft(createModuleDraft(), { newModuleName: ' formatting ', parameterName: 'bad' })
  assert.deepEqual(buildModulePayload('utils', change), { change_domain: 'module', change_type: 'rename_module', target_module_id: 'utils', new_module_name: 'formatting' })
  change = updateModuleDraft(createModuleDraft('remove_module'), { confirmed: true, newModuleName: 'bad' })
  assert.deepEqual(change.operation, { confirmed: true })
  assert.deepEqual(buildModulePayload('utils', change), { change_domain: 'module', change_type: 'remove_module', target_module_id: 'utils' })
})
test('module HTTP workflow reuses original File and fingerprint at all stages', async () => {
  const h = harness(); await ready(h)
  assert.equal(await h.actions.validateChange(), true); assert.equal(await h.actions.analyzeProject(), true)
  assert.equal(h.state().report.change_domain, 'module')
  assert.equal(h.state().report.summary.direct_import_count, 1)
  assert.deepEqual(h.calls.map(c => c[0]), ['inspect', 'validate', 'analyze'])
  h.calls.forEach(call => assert.equal(call[1], original))
  h.calls.slice(1).forEach(call => assert.equal(call[3], fixture.inspect.project_fingerprint))
})
test('domain change clears selection, operation, validation, report and advances revision', async () => {
  const h = harness(); await ready(h); await h.actions.validateChange(); await h.actions.analyzeProject()
  const revision = h.state().revision
  h.actions.selectDomain('function')
  assert.equal(h.state().change.changeType, 'add_required_parameter'); assert.equal(h.state().selectedModuleId, null)
  assert.equal(h.state().validation, null); assert.equal(h.state().report, null); assert.equal(h.state().file, original)
  assert.equal(h.state().revision, revision + 1)
  h.actions.selectDomain('module'); assert.deepEqual(h.state().change.operation, { newModuleName: '' })
})
test('unsupported module cannot be selected, and no functions are required for module selection', async () => {
  const inspect = structuredClone(fixture.inspect); inspect.symbols = []; inspect.module_inventory.modules[0].selectable = false
  const h = harness({ inspect: async () => inspect }); await ready(h)
  h.actions.selectModule(inspect.module_inventory.modules[0].module_id)
  assert.equal(h.state().selectedModuleId, null)
  h.actions.selectModule('utils'); assert.equal(h.state().selectedModuleId, 'utils')
})
test('remove confirmation is required and excluded from API payload', async () => {
  const h = harness(); await ready(h); h.actions.selectChangeType('remove_module')
  assert.equal(await h.actions.validateChange(), false); assert.equal(h.state().error.code, 'confirmation_required')
  h.actions.updateChange({ confirmed: true }); assert.equal(h.state().validation, null)
  assert.deepEqual(buildChangePayload(h.state()), { change_domain: 'module', change_type: 'remove_module', target_module_id: 'utils' })
})
test('late module Validate cannot overwrite switched function domain even ignoring abort', async () => {
  let resolve, signal
  const h = harness({ validate: (_f, _c, _p, options) => { signal = options.signal; return new Promise(r => { resolve = r }) } })
  await ready(h); const request = h.actions.validateChange(); h.actions.selectDomain('function')
  assert.equal(signal.aborted, true); resolve(structuredClone(fixture.validation)); assert.equal(await request, false)
  assert.equal(h.state().validation, null); assert.equal(h.state().changeDomain, 'function')
})
test('late module Analyze cannot restore old evidence after switching module operation', async () => {
  let resolve
  const h = harness({ analyze: () => new Promise(r => { resolve = r }) }); await ready(h); await h.actions.validateChange()
  const request = h.actions.analyzeProject(); h.actions.selectChangeType('remove_module'); resolve(structuredClone(fixture.report))
  assert.equal(await request, false); assert.equal(h.state().report, null); assert.equal(h.state().validation, null)
})
for (const tamper of [v => { v.change_spec.before.source_hash = 'f'.repeat(64) }, v => { v.change_spec.after.file = 'fake.py' }, v => { v.change_spec.modifies_source = true }]) {
  test(`module validation rejects contradictory canonical snapshot ${tamper.toString()}`, async () => {
    const response = structuredClone(fixture.validation); tamper(response)
    const h = harness({ validate: async () => response }); await ready(h)
    assert.equal(await h.actions.validateChange(), false); assert.equal(h.state().error.code, 'invalid_response')
  })
}
test('module report fingerprint is checked independently of HTTP success', async () => {
  const report = structuredClone(fixture.report); report.project_fingerprint = '0'.repeat(64)
  const h = harness({ analyze: async () => report }); await ready(h); await h.actions.validateChange()
  assert.equal(await h.actions.analyzeProject(), false); assert.equal(h.state().error.code, 'fingerprint_mismatch')
  assert.equal(h.state().inspect, null); assert.equal(h.state().file, original)
})
test('module evidence and explanation correspond by order, ID, target and actual paths', () => {
  const report = structuredClone(fixture.report), findings = moduleFindings(report)
  assert.equal(findings.length, 3)
  findings.forEach((finding, i) => {
    const evidence = moduleEvidence(report, i, finding); assert.ok(evidence)
    assert.ok(moduleExplanation(report, i, evidence))
  })
  ;[report.evidences[0], report.evidences[1]] = [report.evidences[1], report.evidences[0]]
  assert.equal(moduleEvidence(report, 0, findings[0]), null)
})
test('wrong propagation terminal, source seed, site or explanation index is unavailable', () => {
  for (const tamper of [e => { e.propagation_path[0].modules[0] = 'fake' }, e => { e.propagation_path[0].source_direct_impact = 'fake' }, e => { e.propagation_path[0].import_sites[0].line = 99 }]) {
    const report = structuredClone(fixture.report); tamper(report.evidences[1])
    assert.equal(moduleEvidence(report, 1, moduleFindings(report)[1]), null)
  }
  const report = structuredClone(fixture.report); report.explanations[0].evidence_reference = 'fake'
  assert.equal(moduleExplanation(report, 0, report.evidences[0]), null)
})
test('partial and unavailable preserve real findings without borrowing explanations', () => {
  const report = structuredClone(fixture.report); report.coverage.status = 'partial'; report.evidences[0].status = 'unavailable'
  const evidence = moduleEvidence(report, 0, moduleFindings(report)[0]); assert.ok(evidence)
  assert.equal(moduleExplanation(report, 0, evidence), null)
  assert.equal(moduleFindings(report).length, 3)
})
