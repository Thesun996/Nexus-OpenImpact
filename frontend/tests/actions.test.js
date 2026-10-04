import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ApiError } from '../src/api/client.js'
import { createWorkflowActions } from '../src/state/actions.js'
import { createInitialState, workflowReducer } from '../src/state/workflow.js'
import { buildDraftPayload } from '../src/state/changeDraft.js'

const fixture = (name) => JSON.parse(readFileSync(new URL(`../src/demo/fixtures/${name}.json`, import.meta.url)))
const inspect = { ...fixture('inspect'), project_name: 'actual-project', project_fingerprint: 'a'.repeat(64) }
const validation = { ...fixture('validate'), project_fingerprint: inspect.project_fingerprint }
const report = fixture('analyze')
const original = new File(['different user ZIP bytes'], 'user-selected.zip')
// Canonical changes captured from the six existing Core CLI demos; no runtime mock.
const changeSpecs = JSON.parse(readFileSync(new URL('./fixtures/change-specs.json', import.meta.url)))
function pending() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function harness(overrides = {}) {
  let state = createInitialState()
  const calls = []
  const client = {
    health: async () => ({ status: 'ok', version: '0.1.0' }),
    inspect: async (...args) => { calls.push(['inspect', ...args]); return structuredClone(inspect) },
    validate: async (...args) => { calls.push(['validate', ...args]); return structuredClone(validation) },
    analyze: async (...args) => { calls.push(['analyze', ...args]); return structuredClone(report) },
    ...overrides,
  }
  const actions = createWorkflowActions({
    getState: () => state,
    dispatch: (action) => { state = workflowReducer(state, action) }, client,
    loadDemoFile: async () => new File(['demo'], 'signature_change.zip'),
    demo: { inspect: fixture('inspect'), validation: fixture('validate'), report },
  })
  return { actions, calls, state: () => state }
}
async function ready(h) {
  h.actions.selectFile(original)
  assert.equal(await h.actions.inspectProject(), true)
  h.actions.selectSymbol('utils.format_date')
  h.actions.updateChange({ parameterName: 'timezone' })
}

test('actual workflow sends the original File and server Inspect fingerprint to all stages', async () => {
  const h = harness()
  await ready(h)
  assert.equal(await h.actions.validateChange(), true)
  assert.equal(await h.actions.analyzeProject(), true)
  assert.deepEqual(h.calls.map(([stage]) => stage), ['inspect', 'validate', 'analyze'])
  h.calls.forEach(([, file]) => assert.equal(file, original))
  for (const call of h.calls.slice(1)) {
    assert.equal(call[3], inspect.project_fingerprint)
    assert.deepEqual(call[2], { change_type: 'add_required_parameter', target_symbol_id: 'utils.format_date', added_parameter: { name: 'timezone', kind: 'positional_or_keyword' } })
  }
  assert.equal(h.state().mode, 'project')
  assert.equal(h.state().report.summary.direct_impact_count, 1)
})

test('Inspect success never selects the demo target or sets a default parameter', async () => {
  const h = harness()
  h.actions.selectFile(original)
  await h.actions.inspectProject()
  assert.equal(h.state().selectedSymbolId, null)
  assert.equal(h.state().change.operation.parameterName, '')
  assert.equal(h.state().report, null)
})

test('changing target and receiving zero result removes all previous impacts/evidences/explanations', async () => {
  const zeroValidation = { ...validation, change_spec: { ...validation.change_spec, target_symbol_id: 'page.page',
    added_parameter: { ...validation.change_spec.added_parameter, name: 'zone' },
    before: { ...validation.change_spec.before, name: 'page', parameters: [] },
    after: { ...validation.change_spec.after, name: 'page', parameters: [{ ...validation.change_spec.after.parameters[1], name: 'zone' }] } } }
  const zero = { ...report, change: zeroValidation.change_spec,
    summary: { ...report.summary, direct_impact_count: 0, indirect_1hop_count: 0, indirect_2hop_count: 0 },
    direct_impacts: [], indirect_impacts: [], evidences: [], explanations: [] }
  let target = 'utils.format_date'
  const h = harness({ validate: async () => target === 'page.page' ? zeroValidation : validation, analyze: async () => target === 'page.page' ? zero : report })
  await ready(h); await h.actions.validateChange(); await h.actions.analyzeProject()
  target = 'page.page'
  h.actions.selectSymbol(target)
  assert.equal(h.state().report, null)
  h.actions.updateChange({ parameterName: 'zone' })
  await h.actions.validateChange(); await h.actions.analyzeProject()
  assert.equal(h.state().report.change.target_symbol_id, 'page.page')
  assert.equal(h.state().report.summary.direct_impact_count, 0)
  assert.deepEqual(h.state().report.evidences, [])
  assert.deepEqual(h.state().report.explanations, [])
})

test('repeated Inspect click sends exactly one request while it is pending', async () => {
  const wait = pending(); let count = 0
  const h = harness({ inspect: () => { count++; return wait.promise } })
  h.actions.selectFile(original)
  const first = h.actions.inspectProject()
  assert.equal(h.state().loading.inspect, true)
  assert.equal(await h.actions.inspectProject(), false)
  assert.equal(count, 1)
  wait.resolve(inspect)
  assert.equal(await first, true)
  assert.equal(h.state().loading.inspect, false)
})

test('repeated Analyze click does not create a second concurrent submission', async () => {
  const wait = pending(); let count = 0
  const h = harness({ analyze: () => { count++; return wait.promise } })
  await ready(h); await h.actions.validateChange()
  const first = h.actions.analyzeProject()
  assert.equal(await h.actions.analyzeProject(), false)
  assert.equal(count, 1)
  wait.resolve(report); assert.equal(await first, true)
})

test('a late Inspect response ignoring AbortSignal cannot overwrite a newly selected ZIP', async () => {
  const wait = pending(); let signal
  const h = harness({ inspect: (file, options) => { signal = options.signal; return wait.promise } })
  h.actions.selectFile(original)
  const request = h.actions.inspectProject()
  const replacement = new File(['new bytes'], 'new.zip')
  h.actions.selectFile(replacement)
  assert.equal(signal.aborted, true)
  wait.resolve(inspect)
  assert.equal(await request, false)
  assert.equal(h.state().file, replacement)
  assert.equal(h.state().inspect, null)
  assert.equal(h.state().projectFingerprint, null)
})

test('late Analyze success is ignored after parameter changes even when transport ignores abort', async () => {
  const wait = pending(); let signal
  const h = harness({ analyze: (file, change, fingerprint, options) => { signal = options.signal; return wait.promise } })
  await ready(h); await h.actions.validateChange()
  const request = h.actions.analyzeProject()
  h.actions.updateChange({ parameterName: 'zone' })
  assert.equal(signal.aborted, true)
  wait.resolve(report); assert.equal(await request, false)
  assert.equal(h.state().report, null)
  assert.equal(h.state().validation, null)
  assert.equal(h.state().change.operation.parameterName, 'zone')
})

test('old failed request does not replace error state of a newer project', async () => {
  const wait = pending()
  const h = harness({ inspect: () => wait.promise })
  h.actions.selectFile(original); const request = h.actions.inspectProject()
  h.actions.selectFile(new File(['new'], 'new.zip'))
  wait.reject(new ApiError({ status: 500, code: 'internal_error', message: 'old error' }))
  assert.equal(await request, false)
  assert.equal(h.state().error, null)
})

test('422 Core validation retains structured failed result without allowing Analyze', async () => {
  const failed = { ...validation, change_spec: null, validation: { valid: false, diagnostics: [{ code: 'invalid_after_signature', message: '参数重名' }] } }
  const h = harness({ validate: async () => { throw new ApiError({ status: 422, code: 'invalid_after_signature', message: '参数重名', diagnostics: failed.validation.diagnostics, payload: failed }) } })
  await ready(h)
  assert.equal(await h.actions.validateChange(), false)
  assert.equal(h.state().validation, failed)
  assert.equal(h.state().validation.validation.valid, false)
  assert.equal(h.state().error.status, 422)
  assert.equal(await h.actions.analyzeProject(), false)
  assert.equal(h.state().report, null)
})

test('409 retains original File but clears fingerprint, Symbol, configuration and previous reports', async () => {
  let mismatch = false
  const h = harness({ validate: async () => {
    if (mismatch) throw new ApiError({ status: 409, code: 'fingerprint_mismatch', message: '请重新读取项目' })
    return validation
  } })
  await ready(h); await h.actions.validateChange(); await h.actions.analyzeProject()
  mismatch = true
  assert.equal(await h.actions.validateChange(), false)
  assert.equal(h.state().file, original)
  for (const key of ['inspect', 'projectFingerprint', 'selectedSymbolId', 'validation', 'report']) assert.equal(h.state()[key], null)
  assert.equal(h.state().change.operation.parameterName, '')
  assert.equal(h.state().error.code, 'fingerprint_mismatch')
  assert.equal(await h.actions.inspectProject(), true)
  assert.equal(h.state().error, null)
})

test('Validate must return the same fingerprint even on HTTP success', async () => {
  const h = harness({ validate: async () => ({ ...validation, project_fingerprint: 'b'.repeat(64) }) })
  await ready(h)
  assert.equal(await h.actions.validateChange(), false)
  assert.equal(h.state().error.code, 'fingerprint_mismatch')
  assert.equal(h.state().validation, null)
})

test('network failures never create implicit demo or zero results', async () => {
  const h = harness({ inspect: async () => { throw new ApiError({ code: 'backend_unreachable', message: '无法连接后端' }) } })
  h.actions.selectFile(original)
  assert.equal(await h.actions.inspectProject(), false)
  assert.equal(h.state().mode, 'project')
  assert.equal(h.state().inspect, null)
  assert.equal(h.state().report, null)
  assert.equal(h.state().error.code, 'backend_unreachable')
  assert.equal(h.state().loading.inspect, false)
})

test('safe 500 Analyze response clears stale report and leaves a visible error', async () => {
  let fail = false
  const h = harness({ analyze: async () => {
    if (fail) throw new ApiError({ status: 500, code: 'internal_error', message: '服务内部错误。' })
    return report
  } })
  await ready(h); await h.actions.validateChange(); await h.actions.analyzeProject()
  fail = true
  assert.equal(await h.actions.analyzeProject(), false)
  assert.equal(h.state().report, null)
  assert.equal(h.state().error.code, 'internal_error')
  assert.equal(h.state().loading.analyze, false)
})

test('empty function list remains empty and prevents Validate', async () => {
  const h = harness({ inspect: async () => ({ ...inspect, symbols: [] }) })
  h.actions.selectFile(original); assert.equal(await h.actions.inspectProject(), true)
  assert.deepEqual(h.state().inspect.symbols, [])
  assert.equal(h.state().selectedSymbolId, null)
  assert.equal(await h.actions.validateChange(), false)
  assert.equal(h.state().report, null)
})

test('changing ZIP clears completed results, configuration, error, and retains health independently', async () => {
  const h = harness()
  await h.actions.checkHealth(); await ready(h)
  await h.actions.validateChange(); await h.actions.analyzeProject()
  const next = new File(['new'], 'next.zip'); h.actions.selectFile(next)
  assert.equal(h.state().file, next)
  assert.equal(h.state().change.operation.parameterName, '')
  assert.equal(h.state().selectedSymbolId, null)
  assert.equal(h.state().report, null)
  assert.equal(h.state().error, null)
  assert.equal(h.state().health.status, 'ok')
})

test('health failure stays separate from the current project and manual retry can recover', async () => {
  let fail = true
  const h = harness({ health: async () => {
    if (fail) throw new ApiError({ code: 'backend_unreachable', message: '无法连接后端' })
    return { status: 'ok', version: '0.1.0' }
  } })
  h.actions.selectFile(original)
  assert.equal(await h.actions.checkHealth(), false)
  assert.equal(h.state().file, original)
  assert.equal(h.state().error, null)
  assert.equal(h.state().health.status, 'error')
  fail = false
  assert.equal(await h.actions.checkHealth(), true)
  assert.equal(h.state().health.status, 'ok')
})

for (const [name, spec] of Object.entries(changeSpecs)) {
  test(`validated configuration round-trip preserves original ZIP/fingerprint for ${name}`, async () => {
    const type = spec.change_type
    const operation = type === 'add_required_parameter'
      ? { parameterName: spec.added_parameter.name, kind: spec.added_parameter.kind }
      : { parameterName: spec.operation.parameter_name,
          ...(type === 'rename_parameter' ? { newParameterName: spec.operation.new_parameter_name } : {}) }
    const inspected = { ...inspect, symbols: [{ ...spec.before, symbol_id: spec.target_symbol_id, module: 'utils', file: 'utils.py', line: 1 }] }
    const checked = { ...validation, change_spec: spec }
    const analyzed = { ...report, change: spec }
    const calls = []
    const h = harness({
      inspect: async () => inspected,
      validate: async (...args) => { calls.push(args); return checked },
      analyze: async (...args) => { calls.push(args); return analyzed },
    })
    h.actions.selectFile(original); await h.actions.inspectProject()
    h.actions.selectSymbol(spec.target_symbol_id); h.actions.selectChangeType(type)
    h.actions.updateChange(operation)
    assert.equal(await h.actions.validateChange(), true)
    const payload = buildDraftPayload(spec.target_symbol_id, h.state().change)
    assert.deepEqual(h.state().validatedChange, { revision: h.state().revision, payload })
    assert.equal(await h.actions.analyzeProject(), true)
    for (const [file, sentChange, fingerprint] of calls) {
      assert.equal(file, original)
      assert.equal(fingerprint, inspect.project_fingerprint)
      assert.deepEqual(sentChange, payload)
    }
    assert.deepEqual(calls[0][1], calls[1][1])
  })
}

test('late Validate after add → remove → rename cannot confirm an obsolete configuration', async () => {
  const wait = pending(); let signal
  const h = harness({ validate: (file, change, fingerprint, options) => { signal = options.signal; return wait.promise } })
  await ready(h)
  const first = h.actions.validateChange()
  h.actions.selectChangeType('remove_parameter')
  h.actions.updateChange({ parameterName: 'date' })
  h.actions.selectChangeType('rename_parameter')
  h.actions.updateChange({ parameterName: 'date', newParameterName: 'day' })
  assert.equal(signal.aborted, true)
  wait.resolve(validation)
  assert.equal(await first, false)
  assert.deepEqual(h.state().change, { changeType: 'rename_parameter', operation: { parameterName: 'date', newParameterName: 'day' } })
  assert.equal(h.state().validation, null)
  assert.equal(h.state().validatedChange, null)
  assert.equal(h.state().report, null)
  assert.equal(await h.actions.analyzeProject(), false)
})

test('late Analyze cannot restore counts or evidence after changing type', async () => {
  const wait = pending(); let signal
  const h = harness({ analyze: (file, change, fingerprint, options) => { signal = options.signal; return wait.promise } })
  await ready(h); await h.actions.validateChange()
  const first = h.actions.analyzeProject()
  h.actions.selectChangeType('make_parameter_required')
  assert.equal(signal.aborted, true)
  wait.resolve(report)
  assert.equal(await first, false)
  assert.equal(h.state().report, null)
  assert.equal(h.state().validation, null)
  assert.deepEqual(h.state().change.operation, { parameterName: '' })
})

test('successful HTTP Validate for a different operation is rejected', async () => {
  const h = harness({ validate: async () => ({ ...validation, change_spec: changeSpecs.parameter_removal }) })
  await ready(h)
  assert.equal(await h.actions.validateChange(), false)
  assert.equal(h.state().error.code, 'invalid_response')
  assert.equal(h.state().validation, null)
  assert.equal(await h.actions.analyzeProject(), false)
})

test('top-level add with a contradictory operation discriminator is rejected', async () => {
  const wrong = { ...validation, change_spec: { ...validation.change_spec, operation: { change_type: 'remove_parameter', parameter_name: 'date' } } }
  const h = harness({ validate: async () => wrong })
  await ready(h)
  assert.equal(await h.actions.validateChange(), false)
  assert.equal(h.state().error.code, 'invalid_response')
})

test('Analyze response must preserve the validated canonical signatures', async () => {
  const wrong = structuredClone(report)
  wrong.change.after.parameters[1].has_default = true
  wrong.change.after.parameters[1].default_source = "'UTC'"
  const h = harness({ analyze: async () => wrong })
  await ready(h); await h.actions.validateChange()
  assert.equal(await h.actions.analyzeProject(), false)
  assert.equal(h.state().error.code, 'invalid_response')
  assert.equal(h.state().report, null)
})

test('rename accepts Core Unicode normalization while sending the same validated payload', async () => {
  const spec = structuredClone(changeSpecs.parameter_rename_keyword)
  spec.operation.new_parameter_name = 'delay'
  const h = harness({
    inspect: async () => ({ ...inspect, symbols: [{ ...spec.before, symbol_id: spec.target_symbol_id }] }),
    validate: async () => ({ ...validation, change_spec: spec }), analyze: async () => ({ ...report, change: spec }),
  })
  h.actions.selectFile(original); await h.actions.inspectProject()
  h.actions.selectSymbol(spec.target_symbol_id); h.actions.selectChangeType('rename_parameter')
  h.actions.updateChange({ parameterName: 'timeout', newParameterName: 'ｄｅｌａｙ' })
  assert.equal(await h.actions.validateChange(), true)
  assert.equal(await h.actions.analyzeProject(), true)
  assert.equal(h.state().report.change.operation.new_parameter_name, 'delay')
})

test('non-add Core rejection remains explicit and cannot reuse a previous successful Validate', async () => {
  const h = harness({ validate: async () => { throw new ApiError({ status: 422, code: 'unsupported_parameter_kind', message: '该参数类型暂不支持。' }) } })
  await ready(h)
  h.actions.selectChangeType('rename_parameter')
  h.actions.updateChange({ parameterName: 'date', newParameterName: 'day' })
  assert.equal(await h.actions.validateChange(), false)
  assert.equal(h.state().error.status, 422)
  assert.equal(h.state().error.code, 'unsupported_parameter_kind')
  assert.equal(h.state().validatedChange, null)
  assert.equal(await h.actions.analyzeProject(), false)
})
