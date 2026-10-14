import test from 'node:test'
import assert from 'node:assert/strict'
import { checkedTask, waitForAnalysisTask, waitForPoll } from '../src/state/analysisTask.js'

const task = { id: 'a'.repeat(32), project_snapshot_id: 'b'.repeat(32), status: 'queued', change: { target_symbol_id: 'utils.format_date' } }

test('task polling is bounded and can stop while waiting without a further request', async () => {
  let reads = 0
  const client = { getAnalysisTask: async () => { reads++; return task } }
  await assert.rejects(waitForAnalysisTask(client, task, { timeoutMs: 5 }), error => error.code === 'task_wait_timeout')
  assert.equal(reads, 0)
  const controller = new AbortController()
  const pending = waitForPoll(controller.signal)
  controller.abort()
  await assert.rejects(pending, { name: 'AbortError' })
})

test('polling preserves running and terminal failure without manufacturing a report', async () => {
  const updates = []
  let reads = 0
  await assert.rejects(waitForAnalysisTask({ getAnalysisTask: async () => ++reads === 1
    ? { ...task, status: 'running' } : { ...task, status: 'failed', error_code: 'invalid_after_signature', error_message: '签名不合法' } }, task,
  { pause: async () => {}, onUpdate: value => updates.push(value.status) }), error => error.code === 'invalid_after_signature')
  assert.deepEqual(updates, ['queued', 'running', 'failed'])
})

test('poll responses allow JSON field reordering but reject missing results and unknown status', () => {
  assert.equal(checkedTask({ ...task, change: { b: 2, a: 1 } }, { change: { a: 1, b: 2 } }).id, task.id)
  for (const status of ['succeeded', 'constructor', 'cancelled']) {
    assert.throws(() => checkedTask({ ...task, status }), error => error.code === 'invalid_task_response')
  }
})
