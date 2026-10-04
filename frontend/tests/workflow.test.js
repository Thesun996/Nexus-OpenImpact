import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { buildChangePayload, createInitialState, DEMO_FINGERPRINT, fileError, formatSignature, getSelectedSymbol, isSupportedDemoChange, workflowReducer as reduce } from '../src/state/workflow.js'

const fixture = (name) => JSON.parse(readFileSync(new URL(`../src/demo/fixtures/${name}.json`, import.meta.url), 'utf8'))
const inspect = fixture('inspect')
const validation = fixture('validate')
const report = fixture('analyze')
const file = new File(['zip bytes'], 'original.zip', { type: 'application/zip' })
function demo() {
  return reduce(createInitialState(), { type: 'DEMO_RECEIVED', file, inspect })
}
function completedDemo() {
  let state = demo()
  state = reduce(state, { type: 'VALIDATION_RECEIVED', validation })
  return reduce(state, { type: 'REPORT_RECEIVED', report })
}

test('initial project and refresh have no implicit demo or report', () => {
  const state = createInitialState()
  assert.equal(state.mode, 'project')
  for (const field of ['file', 'inspect', 'projectFingerprint', 'selectedSymbolId', 'validation', 'report']) assert.equal(state[field], null)
})

test('selecting a real ZIP leaves analysis unset and retains the original File', () => {
  const state = reduce(completedDemo(), { type: 'FILE_SELECTED', file })
  assert.equal(state.file, file)
  assert.equal(state.mode, 'project')
  assert.equal(state.inspect, null)
  assert.equal(state.report, null)
  assert.equal(state.projectFingerprint, null)
})

test('File and fingerprint survive function/configuration/validation/report transitions', () => {
  let state = demo()
  state = reduce(state, { type: 'SYMBOL_SELECTED', id: 'utils.format_date' })
  state = reduce(state, { type: 'CHANGE_UPDATED', change: { parameterName: 'timezone' } })
  state = reduce(state, { type: 'VALIDATION_RECEIVED', validation })
  state = reduce(state, { type: 'REPORT_RECEIVED', report })
  assert.equal(state.file, file)
  assert.equal(state.projectFingerprint, inspect.project_fingerprint)
  assert.equal(state.report, report)
})

test('changing Symbol invalidates the old validation and report', () => {
  const state = reduce(completedDemo(), { type: 'SYMBOL_SELECTED', id: 'page.page' })
  assert.equal(getSelectedSymbol(state).name, 'page')
  assert.equal(state.validation, null)
  assert.equal(state.report, null)
  assert.equal(isSupportedDemoChange(state), false)
})

test('changing parameter configuration invalidates old report while retaining ZIP', () => {
  const state = reduce(completedDemo(), { type: 'CHANGE_UPDATED', change: { parameterKind: 'keyword_only' } })
  assert.equal(state.file, file)
  assert.equal(state.validation, null)
  assert.equal(state.report, null)
  assert.equal(isSupportedDemoChange(state), false)
})

test('only the exact explicitly opened demo configuration can use saved responses', () => {
  assert.equal(isSupportedDemoChange(createInitialState()), false)
  const state = demo()
  assert.equal(isSupportedDemoChange(state), true)
  for (const change of [{ parameterName: 'zone' }, { parameterKind: 'positional_only' }, { insertBefore: 'date' }]) {
    assert.equal(isSupportedDemoChange(reduce(state, { type: 'CHANGE_UPDATED', change })), false)
  }
})

test('reset clears File and completed results', () => {
  const state = reduce(completedDemo(), { type: 'RESET' })
  assert.equal(state.file, null)
  assert.equal(state.mode, 'project')
  assert.equal(state.report, null)
})

test('late responses cannot restore an old project after switching ZIP or resetting', () => {
  const old = demo()
  const changed = reduce(old, { type: 'FILE_SELECTED', file: new File(['new'], 'new.zip') })
  for (const action of [
    { type: 'DEMO_RECEIVED', file, inspect }, { type: 'VALIDATION_RECEIVED', validation },
    { type: 'REPORT_RECEIVED', report }, { type: 'REQUEST_FAILED', stage: 'inspect', error: { message: 'old' } },
  ]) assert.equal(reduce(changed, { ...action, revision: old.revision }), changed)
})

test('an unknown or absent Symbol is never silently replaced by demo target', () => {
  assert.equal(getSelectedSymbol(createInitialState()), null)
  const state = reduce(demo(), { type: 'SYMBOL_SELECTED', id: 'absent.f' })
  assert.equal(state.selectedSymbolId, null)
  assert.equal(getSelectedSymbol(state), null)
})

test('simplified change payload preserves kinds and optional insert_before without constructing signatures', () => {
  assert.deepEqual(buildChangePayload(demo()), { target_symbol_id: 'utils.format_date', added_parameter: { name: 'timezone', kind: 'positional_or_keyword' } })
  const state = reduce(demo(), { type: 'CHANGE_UPDATED', change: { parameterKind: 'positional_only', insertBefore: 'date' } })
  assert.deepEqual(buildChangePayload(state), { target_symbol_id: 'utils.format_date', added_parameter: { name: 'timezone', kind: 'positional_only' }, insert_before: 'date' })
})

test('signature display handles empty, positional-only, defaults, keyword-only, and variadics', () => {
  assert.equal(formatSignature({ name: 'page', parameters: [] }), 'page()')
  const p = (name, kind, more = {}) => ({ name, kind, has_default: false, ...more })
  assert.equal(formatSignature({ name: 'f', parameters: [p('a', 'positional_only'), p('b', 'positional_or_keyword', { has_default: true, default_source: '1' }), p('mode', 'keyword_only')] }), 'f(a, /, b=1, *, mode)')
  assert.equal(formatSignature({ name: 'f', parameters: [p('args', 'var_positional'), p('mode', 'keyword_only'), p('kwargs', 'var_keyword')] }), 'f(*args, mode, **kwargs)')
})

test('file checks reject wrong type or oversized uploads without pretending server inspection', () => {
  assert.equal(fileError(new File(['x'], 'source.py')).code, 'zip_required')
  assert.equal(fileError({ name: 'large.zip', size: 5 * 1024 * 1024 + 1 }).code, 'upload_too_large')
  assert.equal(fileError(file), null)
})

test('saved HTTP demo responses are bound to the shipped ZIP and canonical ChangeSpec', () => {
  const bytes = readFileSync(new URL('../public/samples/signature_change.zip', import.meta.url))
  assert.equal(createHash('sha256').update(bytes).digest('hex'), DEMO_FINGERPRINT)
  assert.equal(inspect.project_fingerprint, DEMO_FINGERPRINT)
  assert.equal(validation.project_fingerprint, DEMO_FINGERPRINT)
  assert.deepEqual(validation.change_spec, report.change)
  assert.equal(report.summary.direct_impact_count, 1)
  assert.equal(report.summary.indirect_1hop_count, 1)
  assert.equal(report.summary.indirect_2hop_count, 1)
  assert.equal(report.coverage.status, 'complete')
  assert.equal(report.evidences.length, 3)
  assert.equal(report.explanations.length, 3)
  report.evidences.forEach((evidence, i) => assert.deepEqual(report.explanations[i].evidence, evidence))
})
