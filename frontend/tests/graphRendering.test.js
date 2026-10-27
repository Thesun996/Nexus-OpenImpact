import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'
import { buildChangeGraph, buildEvidenceGraph, buildProjectGraph } from '../src/pages/graphData.js'
import fixture from '../src/demo/fixtures/analyze.json' with { type: 'json' }

let server, GraphPathList, GraphCanvas, graphRelationLabel
before(async () => {
  server = await createServer({
    root: fileURLToPath(new URL('..', import.meta.url)), configFile: false,
    cacheDir: 'node_modules/.vite-graph-rendering', logLevel: 'silent',
    server: { middlewareMode: true }, appType: 'custom',
  })
  ;({ GraphPathList, GraphCanvas, graphRelationLabel } = await server.ssrLoadModule('/src/pages/GraphPage.jsx'))
})
after(async () => { await server?.close() })

test('report branches render as separate accessible paths without inventing a combined chain', () => {
  const paths = [
    { id: 'left', symbols: ['left.entry', 'shared.target'] },
    { id: 'right', symbols: ['right.entry', 'shared.target'] },
  ]
  const html = renderToStaticMarkup(createElement(GraphPathList, { paths }))
  const groups = [...html.matchAll(/role="group" aria-label="调用路径 \d+">(.*?)<\/div>/g)]
  assert.equal(groups.length, 2)
  assert.match(groups[0][1], /left\.entry/)
  assert.doesNotMatch(groups[0][1], /right\.entry/)
  assert.match(groups[1][1], /right\.entry/)
  assert.doesNotMatch(groups[1][1], /left\.entry/)
  for (const group of groups) {
    assert.equal((group[1].match(/shared\.target/g) || []).length, 1)
    assert.equal((group[1].match(/→/g) || []).length, 1)
  }
})

test('confirmed ordinary calls display a call label independently of impact labels', () => {
  const html = renderToStaticMarkup(createElement('span', null, graphRelationLabel('call')))
  assert.equal(html, '<span>已确认调用</span>')
  assert.doesNotMatch(html, /直接影响/)
  assert.equal(graphRelationLabel('direct'), '直接影响')
  assert.equal(graphRelationLabel('indirect_1hop'), '1 层间接影响')
  assert.equal(graphRelationLabel('indirect_2hop'), '2 层间接影响')
})

test('focused canvas renders only the report target and impact paths, retaining the full graph separately', () => {
  const evidence = buildEvidenceGraph(fixture)
  const nodes = [...evidence.nodes, ...Array.from({ length: 100 }, (_, i) => ({ id: `unrelated.f${i}` }))]
  const project = buildProjectGraph({ graph: { nodes, edges: evidence.edges } }, fixture)
  const focused = buildChangeGraph(project, fixture)
  const html = renderToStaticMarkup(createElement(GraphCanvas, { graph: focused, selected: null, onSelect: () => {} }))
  assert.equal((html.match(/role="button"/g) || []).length, 4)
  assert.equal((html.match(/<line /g) || []).length, 3)
  assert.ok(html.includes('utils.format_date，可拖动节点'))
  assert.ok(html.includes('page.page，可拖动节点'))
  assert.doesNotMatch(html, /unrelated\.f/)
  assert.equal(project.nodes.length, 104)
})

test('zero-impact focus renders the real target without borrowing compatible calls', () => {
  const report = { change: { target_symbol_id: 'utils.target' }, direct_impacts: [], indirect_impacts: [], evidences: [] }
  const project = buildProjectGraph({ graph: { nodes: [{ id: 'utils.target' }, { id: 'compatible.caller' }],
    edges: [{ id: 'compatible-call', source: 'compatible.caller', target: 'utils.target', location: { file: 'caller.py', line: 1, column: 0 } }] } }, report)
  const html = renderToStaticMarkup(createElement(GraphCanvas, { graph: buildChangeGraph(project, report), selected: null, onSelect: () => {} }))
  assert.equal((html.match(/role="button"/g) || []).length, 1)
  assert.ok(html.includes('utils.target，可拖动节点'))
  assert.doesNotMatch(html, /compatible\.caller|<line /)
  assert.equal(project.edges.length, 1)
})

for (const count of [100, 505]) {
  test(`${count} project nodes remain rendered in the initial readable 760 by 480 viewport`, () => {
    const nodes = Array.from({ length: count }, (_, index) => ({
      id: `project.function_${index}`, label: `project.function_${index}`, role: 'function',
    }))
    const html = renderToStaticMarkup(createElement(GraphCanvas, {
      graph: { nodes, edges: [] }, selected: null, onSelect: () => {},
    }))
    const viewport = html.match(/<svg[^>]*viewBox="([^"]+)"/)
    assert.ok(viewport)
    assert.deepEqual(viewport[1].split(' ').map(Number), [0, 0, 760, 480])
    assert.equal((html.match(/role="button"/g) || []).length, count)
    for (const node of nodes) assert.ok(html.includes(`aria-label="${node.label}，可拖动节点"`), node.id)
    assert.doesNotMatch(html, /aria-label="暂停动态布局"/)
    assert.match(html, /aria-label="放大关系图"/)
    assert.match(html, /aria-label="恢复默认布局"/)
  })
}
