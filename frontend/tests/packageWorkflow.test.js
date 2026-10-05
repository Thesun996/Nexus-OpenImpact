import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createApiClient } from '../src/api/client.js'
import { createWorkflowActions } from '../src/state/actions.js'
import { createInitialState, workflowReducer } from '../src/state/workflow.js'

const fixture = (name) => JSON.parse(readFileSync(new URL(`../src/demo/fixtures/${name}.json`, import.meta.url)))
const layout = { analysis_root: 'src', mode: 'explicit', import_roots: ['.', 'src'] }
const inspect = { ...fixture('inspect'), analysis_layout: layout }
const validation = { ...fixture('validate'), analysis_layout: layout }
const report = { ...fixture('analyze'), analysis_layout: layout }
const original = new File(['original ZIP'], 'source.zip')

function harness(overrides = {}) {
  let state = createInitialState()
  const calls = []
  const client = Object.fromEntries(Object.entries({ inspect, validate: validation, analyze: report }).map(([name, response]) =>
    [name, async (...args) => { calls.push([name, ...args]); return structuredClone(response) }]))
  const actions = createWorkflowActions({ getState: () => state, dispatch: (action) => { state = workflowReducer(state, action) }, client: { ...client, ...overrides } })
  actions.selectFile(original); actions.setAnalysisRoot('src')
  return { actions, calls, state: () => state }
}

test('all multipart stages repeat the explicit source root and original File without setting a boundary', async () => {
  const calls = []
  const client = createApiClient({ fetchImpl: async (url, options) => { calls.push([url, options]); return new Response('{}') } })
  await client.inspect(original, { analysisRoot: 'src' })
  await client.validate(original, { target_symbol_id: 'pkg.f' }, 'a'.repeat(64), { analysisRoot: 'src' })
  await client.analyze(original, { target_symbol_id: 'pkg.f' }, 'a'.repeat(64), { analysisRoot: 'src' })
  for (const [, options] of calls) {
    assert.equal(options.body.get('file'), original)
    assert.equal(options.body.get('analysis_root'), 'src')
    assert.equal(options.headers['Content-Type'], undefined)
  }
})

test('selected import root is bound to Inspect, validation snapshot and Analyze', async () => {
  const h = harness()
  assert.equal(await h.actions.inspectProject(), true)
  h.actions.selectSymbol('utils.format_date'); h.actions.updateChange({ parameterName: 'timezone' })
  assert.equal(await h.actions.validateChange(), true)
  assert.equal(h.state().validatedChange.analysisRoot, 'src')
  assert.equal(await h.actions.analyzeProject(), true)
  h.calls.forEach((call) => assert.equal(call.at(-1).analysisRoot, 'src'))
  assert.equal(h.state().report.analysis_layout.analysis_root, 'src')
  h.actions.setAnalysisRoot('.')
  for (const key of ['inspect', 'projectFingerprint', 'selectedSymbolId', 'validation', 'validatedChange', 'report', 'error']) assert.equal(h.state()[key], null)
  assert.equal(h.state().file, original)
})

test('changing roots aborts an Inspect and a late response cannot restore old symbols', async () => {
  let resolve, signal
  const h = harness({ inspect: (_, options) => { signal = options.signal; return new Promise(done => { resolve = done }) } })
  const pending = h.actions.inspectProject()
  h.actions.setAnalysisRoot('.')
  assert.equal(signal.aborted, true)
  resolve(inspect)
  assert.equal(await pending, false)
  assert.equal(h.state().inspect, null)
  assert.equal(h.state().analysisRoot, '.')
})

for (const stage of ['inspect', 'validate', 'analyze']) {
  test(`${stage} rejects a successful HTTP response built with a different import root`, async () => {
    const h = harness({ [stage]: async () => structuredClone(fixture(stage === 'validate' ? 'validate' : stage)) })
    if (stage !== 'inspect') {
      await h.actions.inspectProject(); h.actions.selectSymbol('utils.format_date'); h.actions.updateChange({ parameterName: 'timezone' })
      if (stage === 'analyze') await h.actions.validateChange()
    }
    const accepted = await h.actions[stage === 'inspect' ? 'inspectProject' : stage === 'validate' ? 'validateChange' : 'analyzeProject']()
    assert.equal(accepted, false)
    assert.equal(h.state().error.code, 'invalid_response')
    assert.equal(h.state().report, null)
  })
}

test('409 retains root for re-inspection but choosing a different ZIP resets the root', () => {
  let state = { ...createInitialState(), file: original, analysisRoot: 'src' }
  state = workflowReducer(state, { type: 'FINGERPRINT_MISMATCH', error: { code: 'fingerprint_mismatch' } })
  assert.equal(state.analysisRoot, 'src')
  state = workflowReducer(state, { type: 'FILE_SELECTED', file: new File(['new'], 'new.zip') })
  assert.equal(state.analysisRoot, '.')
})

test('re-selecting the active root leaves the in-flight Inspect intact', async () => {
  let resolve, signal
  const h = harness({ inspect: (_, options) => { signal = options.signal; return new Promise(done => { resolve = done }) } })
  const pending = h.actions.inspectProject()
  h.actions.setAnalysisRoot('src')
  assert.equal(signal.aborted, false)
  resolve(inspect)
  assert.equal(await pending, true)
})
