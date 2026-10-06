import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { createInitialState, workflowReducer } from '../src/state/workflow.js'
import { createChangeDraft } from '../src/state/changeDraft.js'

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
    change: { changeType: 'add_required_parameter', operation: { parameterName: 'timezone', kind: 'positional_or_keyword', insertBefore: '' } } }
}
function render(View, state, extras = {}) {
  // The existing shared stepper reads Context. Use its real Provider without
  // changing that contract; server rendering does not run its health effect.
  return renderToStaticMarkup(createElement(WorkflowProvider, null, createElement(View, { state, navigate: noop, onInspect: noop, onOpenDemo: noop,
    onFileChange: noop, onDragOver: noop, onDragLeave: noop, onDrop: noop, onSelect: noop,
    onReset: noop, query: '', onQueryChange: noop, onSelectChangeType: noop, onUpdateChange: noop, onValidate: noop, onAnalyze: noop, ...extras })))
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
  assert.ok(html.includes('分析范围不完整。'))
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

test('selected function has its own configure action without nesting interactive controls', () => {
  const state = project()
  let html = render(FunctionSelectView, state)
  const selectedRow = html.match(/<div class="oi-symbol-row oi-function-row is-selected">(.*?)<\/div>/s)?.[1]
  assert.ok(selectedRow?.includes('utils.format_date'))
  assert.match(selectedRow, /<button[^>]*aria-pressed="true"/)
  assert.match(selectedRow, /<button[^>]*class="primary-action oi-symbol-configure"[^>]*>配置变更<\/button>/)
  for (const [, content] of html.matchAll(/<button\b[^>]*>(.*?)<\/button>/gs)) assert.doesNotMatch(content, /<button\b/)
  assert.equal((html.match(/>配置变更<\/button>/g) || []).length, 1)
  assert.doesNotMatch(html.match(/<footer class="oi-symbol-actions">(.*?)<\/footer>/s)[1], /<button/)
  state.loading.analyze = true
  html = render(FunctionSelectView, state)
  assert.match(html, /<button[^>]*class="primary-action oi-symbol-configure"[^>]*disabled=""[^>]*>配置变更<\/button>/)
})

test('configure remains reachable if search hides the selection and disabled without a selection', () => {
  const state = project()
  let html = render(FunctionSelectView, state, { query: 'dashboard' })
  const footer = html.match(/<footer class="oi-symbol-actions">(.*?)<\/footer>/s)[1]
  assert.match(footer, /<button[^>]*>配置变更<\/button>/)
  assert.doesNotMatch(footer, /disabled=""/)
  assert.equal((html.match(/>配置变更<\/button>/g) || []).length, 1)
  state.selectedSymbolId = null
  html = render(FunctionSelectView, state)
  assert.doesNotMatch(html, /oi-symbol-configure/)
  assert.match(html, /<button[^>]*disabled=""[^>]*>配置变更<\/button>/)
})

test('unvalidated no-argument candidate is labelled as a draft and cannot enable Analyze', () => {
  const state = project()
  state.selectedSymbolId = 'page.page'
  state.change.operation.parameterName = 'zone'
  const html = render(ChangeView, state)
  assert.ok(html.includes('page()'))
  assert.ok(html.includes('参数草稿'))
  assert.ok(html.includes('zone'))
  assert.ok(html.includes('草稿修改后 · 待校验'))
  assert.ok(html.includes('候选签名尚未通过校验'))
  assert.ok(!html.includes('page(, zone)'))
  assert.ok(html.includes('page(<mark class="oi-added-parameter">zone</mark>)'))
  assert.ok(!html.includes('后端校验通过'))
  assert.match(html, /<button[^>]*disabled=""[^>]*>开始分析<\/button>/)
})

test('valid result renders only the backend signature and marks its added parameter', () => {
  const state = project()
  state.selectedSymbolId = 'page.page'
  state.change.operation.parameterName = 'zone'
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

test('all four operation types are explicit accessible choices with one current selection', () => {
  const html = render(ChangeView, project())
  for (const label of ['新增必填参数', '删除参数', '重命名参数', '可选参数改为必填']) {
    assert.match(html, new RegExp(`<input(?=[^>]*name="change-type")(?=[^>]*aria-label="${label}")[^>]*>`))
  }
  assert.equal((html.match(/name="change-type"[^>]*checked=""/g) || []).length, 1)
  assert.ok(!html.includes('name="operation-parameter"'))
})

function parameterProject(type, parameters, operation = {}) {
  const state = project()
  state.change = { ...createChangeDraft(type), operation: { ...createChangeDraft(type).operation, ...operation } }
  state.inspect.symbols = [{ symbol_id: 'utils.format_date', file: 'utils.py', line: 1, name: 'f', parameters }]
  return state
}

const mixedParameters = [
  { name: 'a', kind: 'positional_only', has_default: false },
  { name: 'timeout', kind: 'positional_or_keyword', has_default: true, default_source: '30' },
  { name: 'args', kind: 'var_positional', has_default: false },
  { name: 'mode', kind: 'keyword_only', has_default: true, default_source: 'None' },
  { name: 'kwargs', kind: 'var_keyword', has_default: false },
]

test('remove keeps unsupported variable parameters visible and marks only the removed name', () => {
  const state = parameterProject('remove_parameter', mixedParameters, { parameterName: 'timeout' })
  const html = render(ChangeView, state)
  assert.match(html, /aria-label="选择参数 args"[^>]*disabled=""/)
  assert.match(html, /aria-label="选择参数 kwargs"[^>]*disabled=""/)
  assert.ok(html.includes('当前版本暂不支持删除可变位置参数'))
  assert.ok(html.includes('当前版本暂不支持删除可变关键字参数'))
  assert.ok(html.includes('<del class="oi-removed-parameter">timeout</del>=30'))
  assert.ok(html.includes('− timeout'))
  assert.ok(html.includes('草稿修改后 · 待校验'))
  assert.match(html, /<button[^>]*disabled=""[^>]*>开始分析<\/button>/)
})

test('rename exposes positional-only restriction and displays old-to-new draft without invented legality', () => {
  const state = parameterProject('rename_parameter', mixedParameters, { parameterName: 'timeout', newParameterName: 'delay' })
  const html = render(ChangeView, state)
  assert.match(html, /aria-label="选择参数 a"[^>]*disabled=""/)
  assert.ok(html.includes('当前版本暂不支持重命名仅位置参数'))
  assert.ok(html.includes('新参数名'))
  assert.ok(html.includes('timeout → delay'))
  assert.ok(html.includes('<mark class="oi-added-parameter">delay</mark>=30'))
  assert.ok(!html.includes('后端校验通过'))
})

test('make-required offers every falsey default and leaves required parameters disabled with reasons', () => {
  const defaults = ['None', 'False', '0', '""']
  const state = parameterProject('make_parameter_required', [
    { name: 'required', kind: 'positional_or_keyword', has_default: false },
    ...defaults.map((default_source, index) => ({ name: `p${index}`, kind: 'keyword_only', has_default: true, default_source })),
  ], { parameterName: 'p0' })
  const html = render(ChangeView, state)
  assert.match(html, /aria-label="选择参数 required"[^>]*disabled=""/)
  assert.ok(html.includes('当前没有默认值，已经是必填参数。'))
  for (let index = 0; index < defaults.length; index++) {
    assert.match(html, new RegExp(`aria-label="选择参数 p${index}"[^>]*value="p${index}"`))
    assert.doesNotMatch(html, new RegExp(`aria-label="选择参数 p${index}"[^>]*disabled=""`))
  }
  assert.ok(html.includes('p0=None → p0 · 可选 → 必填'))
  assert.ok(html.includes('<mark class="oi-added-parameter">p0</mark>, p1=False'))
  assert.match(html, /<button[^>]*disabled=""[^>]*>开始分析<\/button>/)
})

test('unsupported-only and empty parameter lists explain recovery instead of hiding choices', () => {
  let state = parameterProject('rename_parameter', mixedParameters.filter(parameter => ['positional_only', 'var_positional', 'var_keyword'].includes(parameter.kind)))
  let html = render(ChangeView, state)
  assert.ok(html.includes('此函数没有可用于当前变更的参数'))
  assert.equal((html.match(/name="operation-parameter"/g) || []).length, 3)
  state = parameterProject('remove_parameter', [])
  html = render(ChangeView, state)
  assert.ok(html.includes('此函数没有参数。'))
  assert.ok(html.includes('返回选择'))
})

test('non-add canonical validation with null added_parameter enables analysis and preserves diagnostics', () => {
  for (const type of ['remove_parameter', 'rename_parameter', 'make_parameter_required']) {
    const operation = { parameterName: 'timeout', ...(type === 'rename_parameter' ? { newParameterName: 'delay' } : {}) }
    const state = parameterProject(type, mixedParameters, operation)
    const before = structuredClone(state.inspect.symbols[0])
    const after = structuredClone(before)
    if (type === 'remove_parameter') after.parameters = after.parameters.filter(parameter => parameter.name !== 'timeout')
    if (type === 'rename_parameter') after.parameters.find(parameter => parameter.name === 'timeout').name = 'delay'
    if (type === 'make_parameter_required') {
      after.parameters.find(parameter => parameter.name === 'timeout').has_default = false
      after.parameters.find(parameter => parameter.name === 'timeout').default_source = null
    }
    state.validation = { validation: { valid: true, diagnostics: [] }, change_spec: { change_type: type,
      target_symbol_id: state.selectedSymbolId, operation: { change_type: type, parameter_name: 'timeout', ...(type === 'rename_parameter' ? { new_parameter_name: 'delay' } : {}) },
      before, after, added_parameter: null }, coverage: { status: 'partial' }, diagnostics: { parse_errors: [{ code: 'syntax_error', file: 'broken.py', message: '真实解析失败' }] } }
    const html = render(ChangeView, state)
    assert.ok(html.includes('已确认变更 · 后端校验通过'))
    assert.ok(html.includes('修改后 · 后端已校验'))
    assert.ok(html.includes('分析范围不完整。'))
    assert.ok(html.includes('broken.py'))
    assert.match(html, /<button[^>]*>开始分析<\/button>/)
    assert.doesNotMatch(html, /<button[^>]*disabled=""[^>]*>开始分析<\/button>/)
  }
})

test('demo visibly restricts the three new types and add name collisions cannot submit a draft', () => {
  const state = project()
  state.mode = 'demo'
  let html = render(ChangeView, state)
  assert.equal((html.match(/<input(?=[^>]*name="change-type")(?=[^>]*disabled="")[^>]*>/g) || []).length, 3)
  assert.ok(html.includes('请上传实际项目使用此类型'))
  state.mode = 'project'
  state.change.operation.parameterName = 'date'
  html = render(ChangeView, state)
  assert.ok(html.includes('当前函数已有同名参数'))
  assert.match(html, /<button[^>]*disabled=""[^>]*>校验变更<\/button>/)
})
