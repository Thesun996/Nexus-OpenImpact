import { ApiError } from '../api/client.js'

const taskStates = ['queued', 'running', 'succeeded', 'failed']
const idPattern = /^[a-f0-9]{32}$/

export function sameChange(left, right) {
  if (left === right) return true
  if (!left || !right || typeof left !== 'object' || typeof right !== 'object'
    || Array.isArray(left) !== Array.isArray(right)) return false
  const keys = Object.keys(left)
  return keys.length === Object.keys(right).length
    && keys.every(key => Object.hasOwn(right, key) && sameChange(left[key], right[key]))
}

function invalidTask() {
  throw new ApiError({ code: 'invalid_task_response', message: '任务响应与本次分析不一致，请刷新任务列表。' })
}

export function checkedTask(task, expected = {}) {
  if (!task || !idPattern.test(task.id) || !idPattern.test(task.project_snapshot_id)
    || !taskStates.includes(task.status) || !task.change || typeof task.change !== 'object' || Array.isArray(task.change)
    || (expected.id && task.id !== expected.id)
    || (expected.project_snapshot_id && task.project_snapshot_id !== expected.project_snapshot_id)
    || (expected.change && !sameChange(task.change, expected.change))
    || (task.status === 'succeeded' && !idPattern.test(task.result_report_id))) invalidTask()
  return task
}

export async function readTaskReport(client, task, { signal } = {}) {
  checkedTask(task)
  if (task.status !== 'succeeded') invalidTask()
  const record = await client.getReport(task.result_report_id, { signal })
  signal?.throwIfAborted()
  if (record.id !== task.result_report_id || !record.report
    || record.report.project_snapshot_id !== task.project_snapshot_id
    || !/^[a-f0-9]{64}$/.test(record.project_fingerprint)
    || record.report.project_fingerprint !== record.project_fingerprint) invalidTask()
  return record
}

export function waitForPoll(signal, milliseconds = 1000) {
  signal.throwIfAborted()
  return new Promise((resolve, reject) => {
    const finish = () => { signal.removeEventListener('abort', abort); resolve() }
    const timer = setTimeout(finish, milliseconds)
    const abort = () => { clearTimeout(timer); signal.removeEventListener('abort', abort); reject(signal.reason) }
    signal.addEventListener('abort', abort, { once: true })
  })
}

// Only GET requests are repeated. A lost connection never resubmits a task.
export async function waitForAnalysisTask(client, initialTask, {
  signal, onUpdate = () => {}, pause = waitForPoll, timeoutMs = 300000,
} = {}) {
  const controller = new AbortController()
  const abort = () => controller.abort(signal.reason)
  signal?.throwIfAborted()
  signal?.addEventListener('abort', abort, { once: true })
  const timer = setTimeout(() => controller.abort(new ApiError({ code: 'task_wait_timeout',
    message: '任务仍未返回结果，可继续查询或稍后到分析任务中查看。' })), timeoutMs)
  try {
    let task = checkedTask(initialTask)
    while (true) {
      controller.signal.throwIfAborted()
      onUpdate(task)
      if (task.status === 'failed') throw new ApiError({ code: task.error_code || 'analysis_task_failed',
        message: task.error_message || '分析任务失败，请检查配置后重试。' })
      if (task.status === 'succeeded') return await readTaskReport(client, task, { signal: controller.signal })
      await pause(controller.signal)
      controller.signal.throwIfAborted()
      task = checkedTask(await client.getAnalysisTask(task.id, { signal: controller.signal }), initialTask)
    }
  } catch (error) {
    if (controller.signal.aborted) throw controller.signal.reason
    throw error
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
  }
}
