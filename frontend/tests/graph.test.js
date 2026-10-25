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
  assert.deepEqual(buildEvidenceGraph(null), { nodes: [], edges: [], paths: [], supported: false })
  assert.equal(buildEvidenceGraph({ change_domain: 'module' }).supported, false)
})

function projectPayload(calls) {
  const ids = [...new Set(calls.flatMap(call => [call.source, call.target]))]
  return { graph: { nodes: ids.map(id => ({ id, kind: 'function' })), edges: calls } }
}

function directCall(column = 4, caller = 'caller.f') {
  return { caller_symbol_id: caller, target_symbol_id: 'utils.f', file: 'caller.py', line: 2, column, impact_type: 'direct' }
}

function directEvidence(call) {
  return { status: 'available', impact_type: 'direct', target_symbol: call.target_symbol_id,
    location: { file: call.file, line: call.line, column: call.column },
    evidence_reference: `call:${call.file}:${call.line}:${call.column}`, propagation_path: [] }
}

function callEdge(column = 4, source = 'caller.f', target = 'utils.f') {
  return { id: `${source}->${target}:${column}`, source, target,
    location: { file: 'caller.py', line: 2, column } }
}

test('项目图仅高亮真实Direct调用点，同调用者的兼容或既有问题保持普通调用', () => {
  const direct = directCall()
  const report = { change: { target_symbol_id: 'utils.f' }, direct_impacts: [direct],
    pre_existing_problems: [directCall(8)], evidences: [directEvidence(direct)] }
  const graph = buildProjectGraph(projectPayload([callEdge(), callEdge(8), callEdge(12), callEdge(4, 'unrelated.f')]), report)
  assert.deepEqual(graph.edges.map(edge => edge.impactType), ['direct', 'call', 'call', 'call'])
  assert.equal(graph.nodes.find(node => node.id === 'caller.f').role, 'direct')
  assert.equal(graph.nodes.find(node => node.id === 'unrelated.f').role, 'function')
  assert.equal(graph.nodes.find(node => node.id === 'caller.f').kind, 'function')
  assert.ok(graph.edges[0].evidence)
  const wrongIdentity = buildProjectGraph(projectPayload([callEdge(), { ...callEdge(), location: { ...callEdge().location, file: 'other.py' } },
    { ...callEdge(), location: { ...callEdge().location, line: 3 } }, callEdge(4, 'caller.f', 'other.f')]), report)
  assert.deepEqual(wrongIdentity.edges.map(edge => edge.impactType), ['direct', 'call', 'call', 'call'])
})

test('没有Direct记录或缺少精确位置时，调用目标相同也不猜测影响', () => {
  const incomplete = { ...directCall(), column: undefined }
  for (const report of [null, { change: { target_symbol_id: 'utils.f' }, direct_impacts: [] },
    { change: { target_symbol_id: 'utils.f' }, direct_impacts: [incomplete] },
    { change_domain: 'module', direct_impacts: [directCall()] }]) {
    assert.equal(buildProjectGraph(projectPayload([callEdge()]), report).edges[0].impactType, 'call')
  }
})

test('回退图保留同一行不同列的Direct，并以真实独立路径表示分支', () => {
  const calls = [directCall(4), directCall(14), directCall(4, 'other.f')]
  const graph = buildEvidenceGraph({ direct_impacts: calls, evidences: calls.map(directEvidence) })
  assert.equal(graph.edges.length, 3)
  assert.deepEqual(graph.edges.map(edge => edge.location.column), [4, 14, 4])
  assert.equal(new Set(graph.edges.map(edge => edge.id)).size, 3)
  assert.deepEqual(graph.paths.map(path => path.symbols), [
    ['caller.f', 'utils.f'], ['caller.f', 'utils.f'], ['other.f', 'utils.f'],
  ])
  assert.equal(new Set(graph.paths.map(path => path.id)).size, 3)
})

test('报告Evidence身份不符时不借用别的证据或传播路径', () => {
  const report = structuredClone(fixture)
  report.evidences[0].location.column += 1
  report.evidences[1].propagation_path[0].symbols[0] = 'invented.f'
  const graph = buildEvidenceGraph(report)
  assert.equal(graph.edges.find(edge => edge.impactType === 'direct').evidence, null)
  assert.ok(graph.nodes.every(node => node.id !== 'invented.f'))
  assert.ok(graph.paths.every(path => path.symbols[0] !== 'invented.f'))
})

test('共享传播调用点去重，保留Direct优先级并拒绝无证据的间接高亮', () => {
  const report = structuredClone(fixture)
  report.indirect_impacts.push(structuredClone(report.indirect_impacts[1]))
  report.evidences.push(structuredClone(report.evidences[2]))
  const fallback = buildEvidenceGraph(report)
  assert.equal(fallback.edges.length, 3)
  assert.equal(fallback.paths.length, 3)
  assert.equal(fallback.edges.find(edge => edge.target === 'utils.format_date').impactType, 'direct')
  const payload = { graph: { nodes: fallback.nodes.map(node => ({ id: node.id })),
    edges: fallback.edges.map(edge => ({ id: edge.id, source: edge.source, target: edge.target, location: edge.location })) } }
  const graph = buildProjectGraph(payload, report)
  assert.deepEqual(graph.edges.map(edge => edge.impactType), ['direct', 'indirect_1hop', 'indirect_2hop'])
  assert.equal(graph.nodes.find(node => node.id === 'dashboard.dashboard').role, 'upstream')
  const noEvidence = buildProjectGraph(payload, { ...report, evidences: [] })
  assert.deepEqual(noEvidence.edges.map(edge => edge.impactType), ['direct', 'call', 'call'])
})

test('传播边按真实路径深度标识，末端调用缺少Direct记录时不推测Direct', () => {
  const report = structuredClone(fixture)
  // A valid 2-hop path still proves its intermediate edge when a separate
  // 1-hop Evidence slot is unavailable; it does not make that edge 2-hop.
  report.evidences[1] = null
  const graph = buildEvidenceGraph(report)
  assert.equal(graph.edges.find(edge => edge.source === 'dashboard.dashboard').impactType, 'indirect_1hop')
  assert.equal(graph.edges.find(edge => edge.source === 'page.page').impactType, 'indirect_2hop')
  const indirectOnly = { ...fixture, direct_impacts: [], evidences: fixture.evidences.slice(1) }
  assert.equal(buildEvidenceGraph(indirectOnly).edges.find(edge => edge.target === 'utils.format_date').impactType, 'call')
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
