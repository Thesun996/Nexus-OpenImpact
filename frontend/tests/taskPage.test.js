import test, { after, before } from 'node:test'
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

let server, matchesTaskFilter, taskChangeLabel, taskStatusGuidance, taskStatusLabel, taskTargetLabel

before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), configFile: false,
    cacheDir: 'node_modules/.vite-task-page-tests', logLevel: 'silent', server: { middlewareMode: true }, appType: 'custom' })
  ;({ matchesTaskFilter, taskChangeLabel, taskStatusGuidance, taskStatusLabel, taskTargetLabel } = await server.ssrLoadModule('/src/pages/AnalysisTasksPage.jsx'))
})

after(async () => { await server?.close() })

test('task status labels expose bounded Chinese states', () => {
  assert.equal(taskStatusLabel('queued'), '排队中')
  assert.equal(taskStatusLabel('running'), '分析中')
  assert.equal(taskStatusLabel('succeeded'), '已完成')
  assert.equal(taskStatusLabel('failed'), '失败')
  assert.equal(taskStatusLabel('other'), '未知状态')
})

test('queued task guidance explains the local worker dependency without resubmitting', () => {
  assert.match(taskStatusGuidance('queued'), /Worker/)
  assert.match(taskStatusGuidance('running'), /静态分析/)
  assert.match(taskStatusGuidance('failed'), /重试/)
})

test('task target label uses stable change identifiers only', () => {
  assert.equal(taskTargetLabel({ target_symbol_id: 'utils.format_date' }), 'utils.format_date')
  assert.equal(taskTargetLabel({ target_module: 'dashboard' }), 'dashboard')
  assert.equal(taskTargetLabel({ target_module_id: 'dashboard' }), 'dashboard')
  assert.equal(taskTargetLabel({ target_symbol: 'settings.TIMEOUT' }), 'settings.TIMEOUT')
  assert.equal(taskTargetLabel({}), '目标未记录')
})

test('task change label summarizes operation without mutating change payload', () => {
  const change = { operation: { change_type: 'rename_parameter', parameter_name: 'timeout' } }
  const beforeSnapshot = JSON.stringify(change)
  assert.equal(taskChangeLabel(change), '重命名参数 · timeout')
  assert.equal(JSON.stringify(change), beforeSnapshot)
  assert.equal(taskChangeLabel({ change_type: 'add_required_parameter', added_parameter: { name: 'timezone' } }), '新增必填参数 · timezone')
  assert.equal(taskChangeLabel({}), '变更类型未知')
})

test('task filters use status and stable task metadata', () => {
  const task = { id: 'task-123', status: 'failed', project_snapshot_id: 'snapshot-456',
    change: { target_symbol_id: 'utils.format_date', change_type: 'add_required_parameter', added_parameter: { name: 'timezone' } } }
  assert.equal(matchesTaskFilter(task, '', ''), true)
  assert.equal(matchesTaskFilter(task, 'format timezone', 'failed'), true)
  assert.equal(matchesTaskFilter(task, 'snapshot-456', ''), true)
  assert.equal(matchesTaskFilter(task, 'format', 'succeeded'), false)
  assert.equal(matchesTaskFilter(task, 'missing', ''), false)
})
