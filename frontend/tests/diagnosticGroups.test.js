import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'
import { diagnosticEntries, groupDiagnostics } from '../src/presentation/diagnostics.js'

let server, DiagnosticsList, ReportDiagnostics
before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), configFile: false,
    cacheDir: 'node_modules/.vite-diagnostic-tests', logLevel: 'silent', server: { middlewareMode: true }, appType: 'custom' })
  ;({ DiagnosticsList } = await server.ssrLoadModule('/src/pages/PageParts.jsx'))
  ;({ ReportDiagnostics } = await server.ssrLoadModule('/src/components/report/ReviewNotes.jsx'))
})
after(async () => { await server?.close() })
const render = (component, props) => renderToStaticMarkup(createElement(component, props))
const group = diagnostics => groupDiagnostics(diagnosticEntries(diagnostics))

test('unknown project targets and aliases never become confirmed external dependencies', () => {
  const diagnostics = { unresolved_calls: [{ expression: 'len(values)', reason: 'name_not_indexed' },
    { expression: 'external_alias.run()', reason: 'import_binding_unresolved' }],
    unresolved_imports: [{ local_name: 'heapq', reason: 'module_not_in_project' }] }
  const result = group(diagnostics)
  assert.equal(result.length, 1)
  assert.equal(result[0].id, 'target')
  assert.equal(result[0].entries.length, 3)
  assert.ok(result[0].description.includes('不能直接认定与本次变更无关'))
  assert.ok(result[0].description.includes('现有记录不足以区分'))
})

test('bindings, object/dynamic calls and analysis gaps are separated by actual reasons', () => {
  const result = group({ unresolved_calls: [
    { reason: 'local_name_shadows_target' }, { reason: 'module_name_rebound' },
    { reason: 'module_binding_missing' }, { reason: 'class_namespace_unresolved' },
    { reason: 'module_level_call' },
  ], unresolved_imports: [{ reason: 'dynamic_import' }, { reason: 'ambiguous_project_module' }],
  parse_errors: [{ kind: 'syntax_error' }] })
  assert.deepEqual(result.map(({ id, entries }) => [id, entries.length]), [['coverage', 2], ['binding', 3], ['dynamic', 3]])
})

test('only explicit builtin evidence uses the recognized outside-target group', () => {
  assert.equal(group([{ reason: 'builtin', expression: 'len' }])[0].id, 'external')
  assert.equal(group([{ reason: 'standard_library_name_collision' }])[0].id, 'binding')
})

test('grouping retains duplicates, unknown categories, source positions and the original payload', () => {
  const call = { file: 'pkg/very_long_module.py', line: 7, column: 0, expression: 'callback(value)', reason: 'local_name_shadows_target' }
  const diagnostics = { unresolved_calls: [call, { ...call }], future_diagnostics: [{ reason: 'future_reason', file: 'new.py', line: 9 }],
    inventory: ['保留原始文本'], metadata: { notARecordList: true } }
  const before = structuredClone(diagnostics)
  const entries = diagnosticEntries(diagnostics), result = groupDiagnostics(entries)
  assert.equal(entries.length, 4)
  assert.equal(result.flatMap(item => item.entries).length, 4)
  assert.equal(result.find(item => item.id === 'binding').entries.length, 2)
  assert.equal(result.find(item => item.id === 'other').entries.length, 2)
  assert.deepEqual(diagnostics, before)
  assert.equal(result.find(item => item.id === 'binding').entries[0].detail.column, 0)
})

test('project diagnostic disclosures preserve every location, expression and technical reason safely', () => {
  const diagnostics = { unresolved_calls: [{ file: 'caller.py', line: 3, column: 0,
    expression: 'callback("<img src=x onerror=alert(1)>")', reason: 'local_name_shadows_target' }],
  unresolved_imports: [{ file: 'caller.py', line: 1, local_name: 'heapq', reason: 'module_not_in_project' }] }
  const html = render(DiagnosticsList, { diagnostics })
  assert.equal((html.match(/class="oi-diagnostic-group"/g) || []).length, 2)
  assert.equal((html.match(/class="diagnostic-item"/g) || []).length, 2)
  assert.ok(html.includes('caller.py:3:0'))
  assert.ok(html.includes('本地绑定名称：<code>heapq</code>'))
  assert.ok(html.includes('绑定歧义与名称遮蔽'))
  assert.ok(html.includes('目标未确认（可能含项目外依赖）'))
  assert.ok(html.includes('local_name_shadows_target'))
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'))
  assert.ok(!html.includes('<img'))
  assert.ok(!html.includes('class="oi-diagnostic-group" open'))
})

test('source errors start expanded, while validation/error arrays remain immediately visible', () => {
  const grouped = render(DiagnosticsList, { diagnostics: { parse_errors: [{ file: 'bad.py', line: 1, kind: 'syntax_error', message: '真实语法错误' }] } })
  assert.ok(grouped.includes('class="oi-diagnostic-group" open=""'))
  assert.ok(grouped.includes('bad.py:1'))
  const flat = render(DiagnosticsList, { diagnostics: [{ code: 'invalid_signature', message: '签名不合法' }] })
  assert.ok(!flat.includes('oi-diagnostic-group'))
  assert.ok(flat.includes('签名不合法'))
})

test('empty groups never create false records or contradictory error success messages', () => {
  assert.deepEqual(group({ unresolved_calls: [], unresolved_imports: [] }), [])
  assert.equal(render(DiagnosticsList, { diagnostics: {}, showEmptyState: false }), '')
  assert.equal(render(DiagnosticsList, { diagnostics: {} }), '<p>未发现诊断项。</p>')
})

test('report remainder does not duplicate unresolved calls or mutate Core statistics and coverage', () => {
  const report = { summary: { unresolved_call_count: 2, direct_impact_count: 0 }, coverage: { status: 'partial' },
    diagnostics: { unresolved_calls: [{ expression: 'unique_callback()', reason: 'local_name_shadows_target' }, { reason: 'unknown_target' }],
      unresolved_imports: [{ local_name: 'alias', file: 'client.py', line: 1, reason: 'module_not_in_project' }] } }
  const before = structuredClone(report), html = render(ReportDiagnostics, { report })
  assert.ok(html.includes('1 条诊断记录'))
  assert.ok(!html.includes('unique_callback'))
  assert.ok(html.includes('未确认调用已在上方单独分组'))
  assert.ok(html.includes('client.py:1'))
  assert.deepEqual(report, before)
})
