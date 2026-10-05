import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { parameterKindLabel, reasonLabel, diagnosticLabel, statusLabel } from '../src/presentation/labels.js'
import { createInitialState } from '../src/state/workflow.js'

let server, ChangeView, WorkflowProvider, ErrorNotice, DiagnosticsList, ReportResults
const noop = () => {}
const inspect = JSON.parse(readFileSync(new URL('../src/demo/fixtures/inspect.json', import.meta.url)))
before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), configFile: false,
    cacheDir: 'node_modules/.vite-localization-tests', logLevel: 'silent', server: { middlewareMode: true }, appType: 'custom' })
  ;({ ChangeView } = await server.ssrLoadModule('/src/pages/ChangePage.jsx'))
  ;({ WorkflowProvider } = await server.ssrLoadModule('/src/state/WorkflowContext.jsx'))
  ;({ ErrorNotice, DiagnosticsList } = await server.ssrLoadModule('/src/pages/PageParts.jsx'))
  ;({ ReportResults } = await server.ssrLoadModule('/src/pages/ReportPage.jsx'))
})
after(async () => { await server?.close() })
const render = (View, props) => renderToStaticMarkup(createElement(WorkflowProvider, null, createElement(View, props)))
// These fixtures have no nested disclosures. Assert the primary content and
// technical details separately, rather than treating HTML attribute values as UI.
const primary = html => html.replace(/<details\b[^>]*>[\s\S]*?<\/details>/g, '')

test('all five parameter kinds receive Chinese labels; unknown kinds are not invented', () => {
  assert.deepEqual(['positional_or_keyword', 'positional_only', 'keyword_only', 'var_positional', 'var_keyword'].map(parameterKindLabel),
    ['普通位置或关键字参数', '仅位置参数', '仅关键字参数', '可变位置参数（*args）', '可变关键字参数（**kwargs）'])
  assert.equal(parameterKindLabel('future_kind'), '参数类型未识别')
  assert.equal(statusLabel('complete'), '完整')
  assert.equal(statusLabel('partial'), '不完整')
})

test('configuration keeps original option values and draft while translating help and status copy', () => {
  const state = { ...createInitialState(), inspect: structuredClone(inspect), selectedSymbolId: 'utils.format_date',
    change: { changeType: 'add_required_parameter', operation: { parameterName: 'timezone', kind: 'positional_or_keyword', insertBefore: '' } } }
  const before = structuredClone(state)
  const html = render(ChangeView, { state, onSelectChangeType: noop, onUpdateChange: noop, onValidate: noop, onAnalyze: noop, navigate: noop })
  assert.ok(html.includes('<option value="positional_or_keyword" selected="">普通位置或关键字参数</option>'))
  assert.ok(!html.includes('<code>positional_or_keyword</code>'))
  assert.ok(html.includes('插入到指定参数之前'))
  assert.ok(!html.includes('对应 insert_before'))
  assert.ok(html.includes('format_date(date'))
  assert.deepEqual(state, before)
})

test('errors translate known field messages and retain exact original text in closed technical details', () => {
  const error = { code: 'invalid_change_config', message: 'target_symbol_id 必须是非空字符串。' }
  const html = render(ErrorNotice, { error })
  assert.ok(primary(html).includes('变更配置无效'))
  assert.ok(primary(html).includes('请提供目标函数或符号的完整标识'))
  assert.ok(!primary(html).includes('target_symbol_id'))
  assert.ok(html.includes('<details><summary>技术详情</summary>'))
  assert.ok(html.includes(error.message))
  assert.ok(html.includes(error.code))
})

test('diagnostic codes are explained without losing source locations or original identifiers', () => {
  const diagnostics = [{ code: 'relative_import_unsupported', reason: 'relative_import_unsupported', file: 'report.py', line: 3,
    import_expression: 'from .utils import format_date' }]
  const before = structuredClone(diagnostics)
  const html = render(DiagnosticsList, { diagnostics })
  assert.ok(primary(html).includes('相对导入暂不支持，需要人工检查'))
  assert.ok(primary(html).includes('report.py:3'))
  assert.ok(primary(html).includes('from .utils import format_date'))
  assert.ok(!primary(html).includes('relative_import_unsupported'))
  assert.ok(html.includes('relative_import_unsupported'))
  assert.deepEqual(diagnostics, before)
})

test('unknown diagnostics remain visible and inspectable without presenting internal codes as explanations', () => {
  const html = render(DiagnosticsList, { diagnostics: [{ code: 'future_internal_code', reason: 'future_binding_reason' }] })
  assert.ok(primary(html).includes('需要检查的诊断'))
  assert.ok(primary(html).includes('暂未提供中文说明'))
  assert.ok(!primary(html).includes('future_internal_code'))
  assert.ok(html.includes('future_binding_reason'))
  assert.equal(diagnosticLabel('fingerprint_mismatch'), '项目版本不一致')
  assert.equal(reasonLabel('当前调用缺少参数 timezone。'), '当前调用缺少参数 timezone。')
})

for (const domain of ['module', 'symbol']) {
  test(`${domain} report translates binding reasons while preserving report and evidence`, () => {
    const fixture = JSON.parse(readFileSync(new URL(`./fixtures/${domain}-responses.json`, import.meta.url)))
    const report = fixture.report, before = structuredClone(report)
    const html = render(ReportResults, { report })
    const code = domain === 'module' ? 'module_not_in_project' : 'symbol_not_in_project'
    assert.ok(!primary(html).includes(code))
    assert.ok(primary(html).includes(domain === 'module' ? '无法确认项目内目标模块' : '无法确认项目内目标符号'))
    assert.ok(html.includes(code))
    assert.ok(html.includes(report.evidences[0].source_snippet.replaceAll('&', '&amp;').replaceAll('"', '&quot;')))
    assert.deepEqual(report, before)
  })
}
