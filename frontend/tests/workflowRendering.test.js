import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { createInitialState, workflowReducer } from '../src/state/workflow.js'

let server, UploadView, FunctionSelectView, ChangeView, SignatureText, WorkflowProvider
const inspect = JSON.parse(readFileSync(new URL('../src/demo/fixtures/inspect.json', import.meta.url), 'utf8'))
const validated = JSON.parse(readFileSync(new URL('../src/demo/fixtures/validate.json', import.meta.url), 'utf8'))
const noop = () => {}

before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), configFile: false,
    cacheDir: 'node_modules/.vite-workflow-rendering-tests', logLevel: 'silent', server: { middlewareMode: true }, appType: 'custom' })
  ;({ UploadView } = await server.ssrLoadModule('/src/pages/UploadPage.jsx'))
  ;({ FunctionSelectView } = await server.ssrLoadModule('/src/pages/FunctionSelectPage.jsx'))
  ;({ ChangeView } = await server.ssrLoadModule('/src/pages/ChangePage.jsx'))
  ;({ SignatureText } = await server.ssrLoadModule('/src/components/workflow/WorkflowParts.jsx'))
  ;({ WorkflowProvider } = await server.ssrLoadModule('/src/state/WorkflowContext.jsx'))
})
after(async () => { await server?.close() })

function project() {
  return { ...createInitialState(), file: new File(['zip'], 'chosen-project.zip'), inspect: structuredClone(inspect),
    projectFingerprint: inspect.project_fingerprint, selectedSymbolId: 'utils.format_date',
    change: { parameterName: 'timezone', parameterKind: 'positional_or_keyword', insertBefore: '' } }
}
function render(View, state, extras = {}) {
  // The existing shared stepper reads Context. Use its real Provider without
  // changing that contract; server rendering does not run its health effect.
  return renderToStaticMarkup(createElement(WorkflowProvider, null, createElement(View, { state, navigate: noop, onInspect: noop, onOpenDemo: noop,
    onFileChange: noop, onDragOver: noop, onDragLeave: noop, onDrop: noop, onSelect: noop,
    onReset: noop, query: '', onQueryChange: noop, onUpdateChange: noop, onValidate: noop, onAnalyze: noop, ...extras })))
}

test('upload distinguishes no file, selected file and active Inspect without implying success', () => {
  const state = createInitialState()
  let html = render(UploadView, state)
  assert.ok(html.includes('data-upload-state="unselected"'))
  assert.ok(!html.includes('aria-label="已读取项目概览"'))
  state.file = new File(['zip'], 'fresh.zip')
  html = render(UploadView, state)
  assert.ok(html.includes('data-upload-state="selected"'))
  assert.ok(html.includes('fresh.zip'))
  assert.ok(!html.includes('aria-label="已读取项目概览"'))
  state.loading.inspect = true
  html = render(UploadView, state)
  assert.ok(html.includes('data-upload-state="loading"'))
  assert.ok(html.includes('aria-busy="true"'))
  assert.match(html, /<button[^>]*disabled=""[^>]*>正在读取项目…<\/button>/)
})

test('Inspect overview uses the actual file, modules, symbols, coverage and fingerprint', () => {
  const state = project()
  state.inspect.project_name = 'uploaded_custom_project'
  state.inspect.modules = state.inspect.modules.slice(0, 2)
  state.inspect.symbols = state.inspect.symbols.slice(0, 3)
  state.inspect.coverage.status = 'partial'
  const html = render(UploadView, state)
  assert.ok(html.includes('uploaded_custom_project'))
  assert.ok(html.includes('chosen-project.zip'))
  assert.match(html, /<dt>模块<\/dt><dd>2<\/dd>/)
  assert.match(html, /<dt>函数<\/dt><dd>3<\/dd>/)
  assert.ok(html.includes(state.projectFingerprint))
  assert.ok(html.includes('partial：分析范围不完整。'))
  assert.ok(html.includes('更换 ZIP 会清除原项目的选择、校验和报告'))
})

test('failed Inspect stays failed and displays the real diagnostic without a success overview', () => {
  const state = { ...createInitialState(), file: new File(['invalid'], 'bad.zip'),
    error: { stage: 'inspect', code: 'invalid_zip', message: '上传内容不是有效的 ZIP。' } }
  const html = render(UploadView, state)
  assert.ok(html.includes('data-upload-state="failed"'))
  assert.ok(html.includes('invalid_zip'))
  assert.ok(html.includes(state.error.message))
  assert.ok(!html.includes('aria-label="已读取项目概览"'))
})

test('function index shows complete distinct Symbols, files and original structured signatures', () => {
  const state = project()
  state.inspect.symbols = ['a', 'b'].map(module => ({ symbol_id: `${module}.process`, module,
    file: `${module}.py`, line: 2, name: 'process', parameters: [{ name: 'x', kind: 'positional_only', has_default: false },
      { name: 'mode', kind: 'keyword_only', has_default: true, default_source: '"safe"' }] }))
  state.selectedSymbolId = 'b.process'
  const html = render(FunctionSelectView, state)
  for (const module of ['a', 'b']) assert.ok(html.includes(`${module}.process`))
  assert.ok(html.includes('a.py:2'))
  assert.ok(html.includes('b.py:2'))
  assert.ok(html.includes('process(x, /, *, mode=&quot;safe&quot;)'))
  assert.equal((html.match(/aria-pressed="true"/g) || []).length, 1)
})

test('empty project and search with no matches have separate recovery actions', () => {
  const state = project()
  let html = render(FunctionSelectView, state, { query: 'does_not_exist' })
  assert.ok(html.includes('没有匹配的函数'))
  assert.ok(html.includes('清空搜索'))
  state.inspect.symbols = []
  html = render(FunctionSelectView, state)
  assert.ok(html.includes('未发现可支持的模块级函数'))
  assert.ok(html.includes('返回上传项目'))
  assert.ok(!html.includes('清空搜索'))
})

test('unvalidated no-argument change stays a draft without inventing a target signature', () => {
  const state = project()
  state.selectedSymbolId = 'page.page'
  state.change.parameterName = 'zone'
  const html = render(ChangeView, state)
  assert.ok(html.includes('page()'))
  assert.ok(html.includes('参数草稿'))
  assert.ok(html.includes('zone'))
  assert.ok(html.includes('修改后签名待后端校验'))
  assert.ok(!html.includes('page(, zone)'))
  assert.ok(!html.includes('page(zone)'))
  assert.match(html, /<button[^>]*disabled=""[^>]*>开始分析<\/button>/)
})

test('valid result renders only the backend signature and marks its added parameter', () => {
  const state = project()
  state.selectedSymbolId = 'page.page'
  state.change.parameterName = 'zone'
  state.validation = structuredClone(validated)
  const signature = { name: 'page', parameters: [], is_async: false }
  state.validation.change_spec.before = signature
  state.validation.change_spec.after = { ...signature, parameters: [{ name: 'zone', kind: 'keyword_only', has_default: false }] }
  state.validation.change_spec.added_parameter.name = 'zone'
  const html = render(ChangeView, state)
  assert.ok(html.includes('校验通过'))
  assert.ok(html.includes('page(*, <mark class="oi-added-parameter">zone</mark>)'))
  assert.ok(!html.includes('page(, zone)'))
  assert.match(html, /<button[^>]*>开始分析<\/button>/)
})

test('invalid Validate retains actual diagnostics and never enables Analyze', () => {
  const state = project()
  state.validation = { change_spec: { before: { name: 'format_date', parameters: [{ name: 'date', kind: 'positional_or_keyword', has_default: false }] },
    after: { name: 'format_date', parameters: [{ name: 'date', kind: 'positional_or_keyword', has_default: false }, { name: 'date', kind: 'positional_or_keyword', has_default: false }] }, added_parameter: { name: 'date' } },
    validation: { valid: false, diagnostics: [{ code: 'invalid_after_signature', message: '目标签名不符合 Python 参数规则。' }] }, diagnostics: {} }
  const html = render(ChangeView, state)
  assert.ok(html.includes('校验未通过'))
  assert.ok(html.includes('invalid_after_signature'))
  assert.ok(html.includes('目标签名不符合 Python 参数规则。'))
  assert.ok(html.includes('后端候选签名 · 未通过'))
  assert.ok(!html.includes('oi-added-parameter'))
  assert.ok(!html.includes('ChangeSpec 校验通过'))
  assert.match(html, /<button[^>]*disabled=""[^>]*>开始分析<\/button>/)
})

test('updated draft renders no expired validated signature while keeping the original ZIP', () => {
  let state = project()
  state.validation = structuredClone(validated)
  state.report = { stale: true }
  const file = state.file
  state = workflowReducer(state, { type: 'CHANGE_UPDATED', change: { parameterName: 'zone' } })
  const html = render(ChangeView, state)
  assert.ok(html.includes('参数草稿'))
  assert.ok(!html.includes('oi-added-parameter">timezone'))
  assert.equal(state.file, file)
  assert.equal(state.report, null)
  assert.equal(state.validation, null)
})

test('parameter highlighting cannot mark unrelated annotation text or mutate the signature', () => {
  const definition = { name: 'zone', parameters: [{ name: 'a', kind: 'positional_only', has_default: false, annotation_source: 'zone' },
    { name: 'zone', kind: 'keyword_only', has_default: false }] }
  const snapshot = JSON.stringify(definition)
  const html = renderToStaticMarkup(createElement(SignatureText, { definition, addedParameterName: 'zone' }))
  assert.ok(html.includes('zone(a: zone, /, *, <mark class="oi-added-parameter">zone</mark>)'))
  assert.equal(JSON.stringify(definition), snapshot)
})
