import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createApiClient, ApiError } from '../src/api/client.js'
import { createWorkflowActions } from '../src/state/actions.js'
import { createInitialState, getProjectSource, workflowReducer } from '../src/state/workflow.js'

const fixture = name => JSON.parse(readFileSync(new URL(`../src/demo/fixtures/${name}.json`, import.meta.url)))
const snapshot = { id: 'a'.repeat(32), project_id: 'b'.repeat(32), project_fingerprint: 'c'.repeat(64), analysis_root: '.', source_filename: 'saved.zip' }
const identity = { project_id: snapshot.project_id, project_snapshot_id: snapshot.id, project_fingerprint: snapshot.project_fingerprint }
const inspect = { ...fixture('inspect'), ...identity, snapshot }
const validation = { ...fixture('validate'), ...identity }
const report = { ...fixture('analyze'), ...identity }
const zip = new File(['original'], 'saved.zip')
const pending = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }

function harness(overrides = {}) {
  let state = createInitialState()
  const calls = []
  const client = Object.fromEntries(Object.entries({ inspect, validate: validation, analyze: report,
    createProject: { snapshot, inspect, project: { id: snapshot.project_id } } }).map(([key, value]) => [key, async (...args) => {
    calls.push([key, ...args]); return structuredClone(value)
  }]))
  const actions = createWorkflowActions({ getState: () => state, dispatch: action => { state = workflowReducer(state, action) },
    client: { ...client, ...overrides } })
  return { actions, calls, state: () => state }
}
async function ready(h) {
  assert.equal(await h.actions.openSnapshot(snapshot), true)
  h.actions.selectSymbol('utils.format_date')
  h.actions.updateChange({ parameterName: 'timezone' })
}

test('saved snapshot opens, validates and analyzes without any browser File', async () => {
  const h = harness()
  await ready(h)
  assert.equal(h.state().file, null)
  assert.deepEqual(getProjectSource(h.state()), { snapshotId: snapshot.id })
  assert.equal(await h.actions.validateChange(), true)
  assert.equal(await h.actions.analyzeProject(), true)
  assert.deepEqual(h.calls.map(([operation]) => operation), ['inspect', 'validate', 'analyze'])
  for (const [, source] of h.calls) assert.deepEqual(source, { snapshotId: snapshot.id })
  assert.equal(h.state().report.project_snapshot_id, snapshot.id)
})

test('explicit save switches to persisted snapshot; a new upload clears it', async () => {
  const h = harness()
  h.actions.selectFile(zip)
  assert.equal(await h.actions.saveProject(), true)
  assert.equal(h.calls[0][1], zip)
  assert.equal(h.state().snapshot.id, snapshot.id)
  assert.equal(h.state().file, null)
  assert.equal(h.state().selectedSymbolId, null)
  h.actions.setAnalysisRoot('src')
  assert.equal(h.state().analysisRoot, '.')
  h.actions.selectFile(new File(['different'], 'new.zip'))
  assert.equal(h.state().snapshot, null)
  assert.equal(h.state().inspect, null)
  assert.equal(h.state().report, null)
})

test('opening a new snapshot immediately clears earlier report and ignores a late response', async () => {
  const wait = pending(); let first = true
  const h = harness({ inspect: async () => first ? (first = false, wait.promise) : inspect })
  const old = h.actions.openSnapshot({ ...snapshot, id: 'd'.repeat(32) })
  assert.equal(await h.actions.openSnapshot(snapshot), true)
  wait.resolve({ ...inspect, project_snapshot_id: 'd'.repeat(32) })
  assert.equal(await old, false)
  assert.equal(h.state().snapshot.id, snapshot.id)
  await ready(h); await h.actions.validateChange(); await h.actions.analyzeProject()
  const reopening = h.actions.openSnapshot(snapshot)
  assert.equal(h.state().report, null)
  await reopening
})

test('selecting another ZIP while saving cannot switch the new project to the old snapshot', async () => {
  const wait = pending()
  const h = harness({ createProject: () => wait.promise })
  h.actions.selectFile(zip)
  const saving = h.actions.saveProject()
  assert.equal(await h.actions.saveProject(), false)
  const other = new File(['new'], 'other.zip')
  h.actions.selectFile(other)
  wait.resolve({ snapshot, inspect, project: { id: snapshot.project_id } })
  assert.equal(await saving, false)
  assert.equal(h.state().file, other)
  assert.equal(h.state().snapshot, null)
})

test('wrong snapshot identity or root cannot be accepted as a successful inspection', async () => {
  for (const override of [{ project_snapshot_id: 'e'.repeat(32) }, { analysis_layout: { analysis_root: 'src' } }, { project_fingerprint: 'f'.repeat(64) }]) {
    const h = harness({ inspect: async () => ({ ...inspect, ...override }) })
    assert.equal(await h.actions.openSnapshot(snapshot), false)
    assert.equal(h.state().inspect, null)
    assert.equal(h.state().report, null)
  }
})

test('a corrupt or missing snapshot cannot produce phantom analysis success', async () => {
  const h = harness({ analyze: async () => { throw new ApiError({ status: 409, code: 'snapshot_corrupted', message: '快照损坏' }) } })
  await ready(h); await h.actions.validateChange()
  assert.equal(await h.actions.analyzeProject(), false)
  assert.equal(h.state().report, null)
  assert.equal(h.state().error.code, 'snapshot_corrupted')
})

test('every snapshot operation sends no ZIP or root override and forwards cancellation', async () => {
  const controller = new AbortController()
  const source = { snapshotId: snapshot.id }
  const seen = []
  const client = createApiClient({ fetchImpl: async (url, options) => {
    seen.push(url)
    assert.equal(options.method, 'POST')
    assert.equal(options.signal, controller.signal)
    assert.equal(options.body.has('file'), false)
    assert.equal(options.body.has('analysis_root'), false)
    assert.equal(options.body.get('expected_fingerprint'), snapshot.project_fingerprint)
    return new Response('{}', { status: 200 })
  } })
  const options = { signal: controller.signal, analysisRoot: 'src' }
  await client.inspect(source, { ...options, fingerprint: snapshot.project_fingerprint })
  for (const op of ['validate', 'analyze', 'saveReport']) await client[op](source, {}, snapshot.project_fingerprint, options)
  await client.source(source, snapshot.project_fingerprint, { ...options, path: 'report.py' })
  await client.question(source, {}, snapshot.project_fingerprint, { ...options, question: 'why?' })
  await client.questionSuggestions(source, {}, snapshot.project_fingerprint, options)
  assert.deepEqual(seen, ['inspect', 'validate', 'analyze', 'reports', 'source', 'questions', 'question-suggestions'].map(op => `/api/v1/snapshots/${snapshot.id}/${op}`))
})
