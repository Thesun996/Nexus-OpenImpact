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
const taskId = 'd'.repeat(32), reportId = 'e'.repeat(32)
const change = { change_type: 'add_required_parameter', target_symbol_id: 'utils.format_date', added_parameter: { name: 'timezone', kind: 'positional_or_keyword' } }
const task = { id: taskId, project_snapshot_id: snapshot.id, status: 'queued', change }
const record = { id: reportId, project_fingerprint: snapshot.project_fingerprint, report }
const zip = new File(['original'], 'saved.zip')
const pending = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }

function harness(overrides = {}) {
  let state = createInitialState()
  const calls = []
  const client = Object.fromEntries(Object.entries({ inspect, validate: validation, analyze: report,
    createProject: { snapshot, inspect, project: { id: snapshot.project_id } },
    createAnalysisTask: { task }, getAnalysisTask: { ...task, status: 'succeeded', result_report_id: reportId }, getReport: record,
  }).map(([key, value]) => [key, async (...args) => {
    calls.push([key, ...args]); return structuredClone(value)
  }]))
  const actions = createWorkflowActions({ getState: () => state, dispatch: action => { state = workflowReducer(state, action) },
    client: { ...client, ...overrides }, taskPause: async () => {} })
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
  assert.deepEqual(h.calls.map(([operation]) => operation), ['inspect', 'validate', 'createAnalysisTask', 'getAnalysisTask', 'getReport'])
  for (const [, source] of h.calls.slice(0, 2)) assert.deepEqual(source, { snapshotId: snapshot.id })
  assert.deepEqual(h.calls[2].slice(1, 4), [snapshot.id, change, snapshot.project_fingerprint])
  assert.equal(h.state().report.project_snapshot_id, snapshot.id)
  assert.equal(h.state().savedReportId, reportId)
  assert.equal(h.state().analysisTask.status, 'succeeded')
})

test('a deleted saved result creates one replacement task on explicit reanalysis', async () => {
  let deleted = false, submissions = 0, currentTask = task
  const h = harness({
    createAnalysisTask: async () => {
      submissions++
      currentTask = { ...task, id: (submissions === 1 ? 'd' : 'f').repeat(32) }
      return { task: currentTask }
    },
    getAnalysisTask: async id => deleted && id === taskId
      ? { ...task, status: 'failed', error_code: 'report_deleted', result_report_id: null }
      : { ...currentTask, status: 'succeeded', result_report_id: reportId },
    getReport: async () => {
      if (deleted && currentTask.id === taskId) throw new ApiError({ status: 404, code: 'report_not_found' })
      return structuredClone(record)
    },
  })
  await ready(h)
  await h.actions.validateChange()
  assert.equal(await h.actions.analyzeProject(), true)
  deleted = true
  assert.equal(await h.actions.analyzeProject(), true)
  assert.equal(submissions, 2)
  assert.equal(h.state().analysisTask.id, 'f'.repeat(32))
  assert.equal(h.state().error, null)
})

test('a legacy task with a missing report clears its cached identity for a later retry', async () => {
  let removed = false, submissions = 0
  const h = harness({
    createAnalysisTask: async () => { submissions++; return { task } },
    getReport: async () => {
      if (removed) throw new ApiError({ status: 404, code: 'report_not_found', message: '报告已删除' })
      return structuredClone(record)
    },
  })
  await ready(h); await h.actions.validateChange()
  assert.equal(await h.actions.analyzeProject(), true)
  removed = true
  assert.equal(await h.actions.analyzeProject(), false)
  assert.equal(h.state().analysisTask, null)
  assert.equal(h.state().savedReportId, null)
  removed = false
  assert.equal(await h.actions.analyzeProject(), true)
  assert.equal(submissions, 2)
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

test('a directly uploaded ZIP is persisted and analyzed through one task', async () => {
  const h = harness()
  h.actions.selectFile(zip)
  assert.equal(await h.actions.inspectProject(), true)
  h.actions.selectSymbol('utils.format_date')
  h.actions.updateChange({ parameterName: 'timezone' })
  assert.equal(await h.actions.validateChange(), true)
  assert.equal(await h.actions.analyzeProject(), true)
  assert.deepEqual(h.calls.map(([operation]) => operation), ['inspect', 'validate', 'createProject', 'createAnalysisTask', 'getAnalysisTask', 'getReport'])
  assert.equal(h.calls[2][1], zip)
  assert.equal(h.state().file, null)
  assert.equal(h.state().snapshot.id, snapshot.id)
  assert.equal(h.state().analysisTask.status, 'succeeded')
  assert.equal(h.state().savedReportId, reportId)
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
  const h = harness({ getAnalysisTask: async () => ({ ...task, status: 'failed', error_code: 'snapshot_corrupted', error_message: '快照损坏' }) })
  await ready(h); await h.actions.validateChange()
  assert.equal(await h.actions.analyzeProject(), false)
  assert.equal(h.state().report, null)
  assert.equal(h.state().error.code, 'snapshot_corrupted')
})

test('double click creates one task; interrupted polling resumes the same task', async () => {
  const wait = pending(); let polls = 0
  const h = harness({ getAnalysisTask: async () => ++polls === 1 ? wait.promise : { ...task, status: 'succeeded', result_report_id: reportId } })
  await ready(h); await h.actions.validateChange()
  const running = h.actions.analyzeProject()
  assert.equal(await h.actions.analyzeProject(), false)
  wait.resolve(Promise.reject(new ApiError({ code: 'backend_unreachable', message: '连接中断' })))
  assert.equal(await running, false)
  assert.equal(h.state().analysisTask.id, taskId)
  assert.equal(h.state().report, null)
  assert.equal(await h.actions.analyzeProject(), true)
  assert.equal(h.calls.filter(([operation]) => operation === 'createAnalysisTask').length, 1)
  assert.equal(h.state().savedReportId, reportId)
})

test('a late task response cannot overwrite another project or configuration', async () => {
  for (const replace of [h => h.actions.selectFile(zip), h => h.actions.updateChange({ parameterName: 'zone' })]) {
    const wait = pending(); const queried = pending()
    const h = harness({ getAnalysisTask: () => { queried.resolve(); return wait.promise } })
    await ready(h); await h.actions.validateChange()
    const running = h.actions.analyzeProject()
    await queried.promise
    replace(h)
    wait.resolve({ ...task, status: 'succeeded', result_report_id: reportId })
    assert.equal(await running, false)
    assert.equal(h.state().analysisTask, null)
    assert.equal(h.state().report, null)
    assert.equal(h.calls.some(([operation]) => operation === 'getReport'), false)
  }
})

test('task and report must match the submitted snapshot, intent and validated signature', async () => {
  for (const override of [
    { createAnalysisTask: async () => ({ task: { ...task, project_snapshot_id: 'f'.repeat(32) } }) },
    { getAnalysisTask: async () => ({ ...task, id: 'f'.repeat(32), status: 'succeeded', result_report_id: reportId }) },
    { getAnalysisTask: async () => ({ ...task, change: { ...change, target_symbol_id: 'other.fn' } }) },
    { getReport: async () => ({ ...record, id: 'f'.repeat(32) }) },
    { getReport: async () => ({ ...record, report: { ...report, project_snapshot_id: 'f'.repeat(32) } }) },
    { getReport: async () => ({ ...record, report: { ...report, change: { ...report.change, after: { name: 'format_date', parameters: [] } } } }) },
  ]) {
    const h = harness(override); await ready(h); await h.actions.validateChange()
    assert.equal(await h.actions.analyzeProject(), false)
    assert.equal(h.state().report, null)
    assert.equal(h.state().savedReportId, null)
  }
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
