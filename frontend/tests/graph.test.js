import test from 'node:test'
import assert from 'node:assert/strict'
import { buildEvidenceGraph, buildProjectGraph } from '../src/pages/graphData.js'
import { floatingPosition, simulateGraphStep } from '../src/pages/graphMotion.js'
import fixture from '../src/demo/fixtures/analyze.json' with { type: 'json' }

test('关系图只从函数分析证据生成节点和调用边', () => {
  const graph = buildEvidenceGraph(fixture)
  assert.equal(graph.supported, true)
  assert.deepEqual(graph.nodes.map(node => node.id), [
    'page.page', 'dashboard.dashboard', 'report.report', 'utils.format_date',
  ])
  assert.equal(graph.edges.length, 3)
  assert.equal(graph.edges[0].location.file, 'report.py')
  assert.equal(graph.edges[0].location.line, 5)
  assert.ok(graph.edges.every(edge => edge.evidence))
})

test('没有报告或非函数报告时不生成猜测关系', () => {
  assert.deepEqual(buildEvidenceGraph(null), { nodes: [], edges: [], supported: false })
  assert.equal(buildEvidenceGraph({ change_domain: 'module' }).supported, false)
})

test('完整项目图保留所有节点，并把未解析调用放在诊断中', () => {
  const graph = buildProjectGraph({
    graph: { nodes: [{ id: 'a.f', file: 'a.py', line: 1 }], edges: [] },
    diagnostics: { unresolved_calls: [{ expression: 'missing', file: 'a.py', line: 2 }] },
    coverage: { status: 'partial' },
  })
  assert.deepEqual(graph.nodes.map(node => node.id), ['a.f'])
  assert.equal(graph.edges.length, 0)
  assert.equal(graph.unresolved.length, 1)
  assert.equal(graph.coverage.status, 'partial')
})

test('节点轻微漂浮有边界且不改变原始坐标', () => {
  const item = { node: { id: 'report.report' }, x: 280, y: 150 }
  const movements = []
  for (let elapsed = 0; elapsed <= 60000; elapsed += 500) {
    const next = floatingPosition(item, elapsed, 760, 360)
    assert.ok(Math.abs(next.x - item.x) <= 8)
    assert.ok(Math.abs(next.y - item.y) <= 12)
    movements.push(next.x)
    const nearEdge = floatingPosition({ ...item, x: 40, y: 300 }, elapsed, 760, 360)
    assert.ok(nearEdge.x >= 40 && nearEdge.x <= 720)
    assert.ok(nearEdge.y >= 40 && nearEdge.y <= 300)
  }
  assert.ok(new Set(movements).size > 1)
  assert.deepEqual(item, { node: { id: 'report.report' }, x: 280, y: 150 })
})

test('拖动暂停漂浮并从放下的位置连续恢复', () => {
  const item = { node: { id: 'utils.format_date' }, x: 420, y: 200 }
  for (const elapsed of [0, 2000, 9000]) {
    assert.deepEqual(floatingPosition(item, elapsed, 760, 360, true), item)
  }
  const released = { ...item, motionOrigin: 9000 }
  assert.deepEqual(floatingPosition(released, 9000, 760, 360), released)
  const nextFrame = floatingPosition(released, 9034, 760, 360)
  assert.ok(Math.hypot(nextFrame.x - item.x, nextFrame.y - item.y) < 0.2)
})

test('不同节点的漂浮节奏不同，相同时间保持确定位置', () => {
  const first = { node: { id: 'report.report' }, x: 200, y: 150 }
  const second = { ...first, node: { id: 'dashboard.dashboard' } }
  const a = floatingPosition(first, 4000, 760, 360)
  const b = floatingPosition(second, 4000, 760, 360)
  assert.notDeepEqual([a.x, a.y], [b.x, b.y])
  assert.deepEqual(a, floatingPosition(first, 4000, 760, 360))
})

test('力导向布局让相邻节点保持弹性并让重叠节点分离', () => {
  let items = [
    { node: { id: 'a' }, x: 300, y: 180, homeX: 210, homeY: 180, vx: 0, vy: 0 },
    { node: { id: 'b' }, x: 301, y: 180, homeX: 550, homeY: 180, vx: 0, vy: 0 },
  ]
  const edges = [{ source: 'a', target: 'b' }]
  for (let frame = 0; frame < 120; frame += 1) {
    items = simulateGraphStep(items, edges, frame * 34, 760, 360)
  }
  const distance = Math.hypot(items[1].x - items[0].x, items[1].y - items[0].y)
  assert.ok(distance > 80)
  assert.ok(distance < 260)
  assert.ok(items.every(item => item.x >= 40 && item.x <= 720 && item.y >= 40 && item.y <= 300))
})

test('拖动中的节点固定，其他节点仍会响应关系力', () => {
  const items = [
    { node: { id: 'a' }, x: 180, y: 160, homeX: 180, homeY: 160, vx: 2, vy: 1 },
    { node: { id: 'b' }, x: 500, y: 160, homeX: 500, homeY: 160, vx: 0, vy: 0 },
  ]
  const next = simulateGraphStep(items, [{ source: 'a', target: 'b' }], 2000, 760, 360, { draggingId: 'a' })
  assert.deepEqual([next[0].x, next[0].y, next[0].vx, next[0].vy], [180, 160, 0, 0])
  assert.notDeepEqual([next[1].x, next[1].y], [500, 160])
})
