import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { createInitialState } from '../src/state/workflow.js'
import { createModuleDraft } from '../src/state/moduleDraft.js'
const fixture = JSON.parse(readFileSync(new URL('./fixtures/module-responses.json', import.meta.url)))
let server, ModuleSelectView, ChangeView, ReportResults, WorkflowProvider
const noop = () => {}
before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), configFile: false,
    cacheDir: 'node_modules/.vite-module-tests', logLevel: 'silent', server: { middlewareMode: true }, appType: 'custom' })
  ;({ default: ModuleSelectView } = await server.ssrLoadModule('/src/pages/ModuleSelectView.jsx'))
  ;({ ChangeView } = await server.ssrLoadModule('/src/pages/ChangePage.jsx'))
  ;({ ReportResults } = await server.ssrLoadModule('/src/pages/ReportPage.jsx'))
  ;({ WorkflowProvider } = await server.ssrLoadModule('/src/state/WorkflowContext.jsx'))
})
after(async () => { await server?.close() })
function state() { return { ...createInitialState(), changeDomain: 'module', change: createModuleDraft(), selectedModuleId: 'utils', inspect: structuredClone(fixture.inspect), validation: null } }
function render(View, props) {
  return renderToStaticMarkup(createElement(WorkflowProvider, null, createElement(View, { query: '', onQueryChange: noop, onSelect: noop, onSelectDomain: noop,
    onReset: noop, navigate: noop, onSelectChangeType: noop, onUpdateChange: noop, onValidate: noop, onAnalyze: noop, ...props })))
}
test('module inventory comes from Inspect, including visible disabled unsupported candidates', () => {
  const current = state(); current.inspect.module_inventory.modules.push({ module_id: 'pkg', file: 'pkg/__init__.py', selectable: false, reason: 'unsupported_module_layout' })
  const html = render(ModuleSelectView, { state: current })
  assert.ok(html.includes('pkg/__init__.py')); assert.ok(html.includes('首版只支持项目根目录'))
  assert.ok(html.includes('不可选择')); assert.ok(html.includes('选择分析模块'))
  assert.ok(!html.includes('format_date('))
})
test('module rename draft is unvalidated and after layout uses backend canonical data only when valid', () => {
  const current = state(); current.change.operation.newModuleName = 'draft_name'
  let html = render(ChangeView, { state: current }); assert.ok(html.includes('draft_name.py')); assert.ok(html.includes('模块草稿 · 待校验'))
  assert.match(html, /<button[^>]*disabled=""[^>]*>开始分析<\/button>/)
  current.validation = structuredClone(fixture.validation)
  html = render(ChangeView, { state: current }); assert.ok(html.includes('formatting.py')); assert.ok(html.includes('后端校验通过'))
  assert.ok(!html.includes('参数草稿'))
})
test('delete confirmation explains no real source modification and does not construct signatures', () => {
  const current = state(); current.change = createModuleDraft('remove_module')
  const html = render(ChangeView, { state: current })
  assert.ok(html.includes('OpenImpact 不会删除或修改文件')); assert.ok(html.includes('type="checkbox"'))
  assert.ok(!html.includes('format_date(')); assert.match(html, /<button[^>]*disabled=""[^>]*>校验变更<\/button>/)
})
test('module report exposes distinct units, Import evidence and rule explanation without call compatibility', () => {
  const html = render(ReportResults, { report: structuredClone(fixture.report) })
  assert.ok(html.includes('直接导入')); assert.ok(html.includes('Import 源码证据')); assert.ok(html.includes('from utils import format_date'))
  assert.ok(html.includes('规则解释')); assert.ok(html.includes('项目导入绑定变化'))
  assert.ok(!html.includes('调用兼容性变化')); assert.ok(!html.includes('新增必填参数'))
})
test('wrong evidence index downgrades both source and explanation without unsafe HTML', () => {
  const report = structuredClone(fixture.report); report.evidences[0].evidence_reference = 'wrong'
  let html = render(ReportResults, { report })
  assert.ok(html.includes('Evidence unavailable')); assert.ok(html.includes('Explanation unavailable'))
  assert.ok(!html.includes('from utils import format_date'))
  report.evidences[0] = structuredClone(fixture.report.evidences[0]); report.evidences[0].source_snippet = '<script>window.BAD=1</script>'
  html = render(ReportResults, { report }); assert.ok(html.includes('&lt;script&gt;')); assert.ok(!html.includes('<script>'))
})
test('zero partial result is visible without fabricated findings, sources or explanation', () => {
  const report = structuredClone(fixture.report); report.import_impacts = []; report.module_indirect_impacts = []; report.evidences = []; report.explanations = []
  report.summary.direct_import_count = report.summary.indirect_1hop_module_count = report.summary.indirect_2hop_module_count = 0
  report.coverage.status = 'partial'; report.diagnostics.import_diagnostics = [{ code: 'dynamic_import', file: 'x.py', line: 1, message: '人工检查' }]
  const html = render(ReportResults, { report }); assert.ok(html.includes('partial：分析范围不完整')); assert.ok(html.includes('当前没有确定影响'))
  assert.ok(html.includes('dynamic_import')); assert.ok(!html.includes('from utils import format_date'))
})
test('unknown module schema cannot be mistaken for frozen Function report v1', () => {
  const report = structuredClone(fixture.report); report.schema_version = 2
  const html = render(ReportResults, { report }); assert.ok(html.includes('模块报告版本不可识别')); assert.ok(!html.includes('新增必填参数'))
})
