import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { createInitialState } from '../src/state/workflow.js'
import { createSymbolDraft } from '../src/state/symbolDraft.js'
const fixture=JSON.parse(readFileSync(new URL('./fixtures/symbol-responses.json',import.meta.url)))
let server, SymbolSelectView, ChangeView, ReportResults, WorkflowProvider
const noop=()=>{}
before(async()=>{
  server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),configFile:false,cacheDir:'node_modules/.vite-symbol-tests',logLevel:'silent',server:{middlewareMode:true},appType:'custom'})
  ;({default:SymbolSelectView}=await server.ssrLoadModule('/src/pages/SymbolSelectView.jsx'))
  ;({ChangeView}=await server.ssrLoadModule('/src/pages/ChangePage.jsx'))
  ;({ReportResults}=await server.ssrLoadModule('/src/pages/ReportPage.jsx'))
  ;({WorkflowProvider}=await server.ssrLoadModule('/src/state/WorkflowContext.jsx'))
})
after(async()=>{await server?.close()})
const state=()=>({...createInitialState(),changeDomain:'symbol',change:createSymbolDraft(),selectedModuleId:'config',selectedVariableSymbolId:'config.MAX_RETRIES',inspect:structuredClone(fixture.inspect)})
function render(View,props){return renderToStaticMarkup(createElement(WorkflowProvider,null,createElement(View,{query:'',onQueryChange:noop,onSelectModule:noop,onSelectVariableSymbol:noop,onSelectDomain:noop,onReset:noop,navigate:noop,onSelectChangeType:noop,onUpdateChange:noop,onValidate:noop,onAnalyze:noop,...props})))}
test('third domain shows actual module, variable definition and disabled reasons',()=>{
  const current=state(); current.inspect.symbol_inventory.symbols.push({...current.inspect.symbol_inventory.symbols[0],symbol_id:'config.PRIVATE',name:'PRIVATE',selectable:false,reason:'symbol_rebound'})
  const html=render(SymbolSelectView,{state:current}); assert.ok(html.includes('MAX_RETRIES = 3')); assert.ok(html.includes('存在重复定义或全局写入')); assert.ok(html.includes('模块符号变更'))
})
test('symbol candidate preview remains unvalidated and canonical after comes only from Validate',()=>{
  const current=state(); current.change.operation.newSymbolName='DRAFT'
  let html=render(ChangeView,{state:current}); assert.ok(html.includes('DRAFT = 3')); assert.ok(html.includes('符号草稿 · 待校验')); assert.match(html,/<button[^>]*disabled=""[^>]*>开始分析<\/button>/)
  current.validation=structuredClone(fixture.validation); html=render(ChangeView,{state:current}); assert.ok(html.includes('RETRY_LIMIT = 3')); assert.ok(html.includes('后端校验通过'))
})
test('remove UI requires explicit analysis-only confirmation and no fake signature',()=>{
  const current=state(); current.change=createSymbolDraft('remove_module_symbol')
  const html=render(ChangeView,{state:current}); assert.ok(html.includes('OpenImpact 不修改或删除上传文件')); assert.ok(html.includes('type="checkbox"')); assert.ok(!html.includes('format_date('))
})
test('symbol report uses physical references and actual source binding evidence',()=>{
  const html=render(ReportResults,{report:structuredClone(fixture.report)})
  assert.ok(html.includes('直接符号引用')); assert.ok(html.includes('config.MAX_RETRIES')); assert.ok(html.includes('静态符号绑定变化')); assert.ok(!html.includes('函数调用参数不兼容')); assert.ok(!html.includes('新增必填参数'))
})
test('source renders as plain text; mismatch never lends another explanation',()=>{
  const report=structuredClone(fixture.report); report.evidences[0].source_snippet='<script>BAD</script>'
  let html=render(ReportResults,{report}); assert.ok(html.includes('&lt;script&gt;')); assert.ok(!html.includes('<script>'))
  report.evidences[0].evidence_reference='wrong'; html=render(ReportResults,{report}); assert.ok(html.includes('Evidence unavailable')); assert.ok(html.includes('Explanation unavailable'))
})
test('zero partial and unknown schema do not impersonate complete Function reports',()=>{
  const report=structuredClone(fixture.report); report.reference_impacts=[]; report.symbol_indirect_impacts=[]; report.evidences=[]; report.explanations=[]; report.coverage.status='partial'
  for(const key of Object.keys(report.summary))report.summary[key]=0
  let html=render(ReportResults,{report}); assert.ok(html.includes('当前没有确定影响')); assert.ok(html.includes('零结果不证明项目没有其他影响'))
  report.schema_version=2; html=render(ReportResults,{report}); assert.ok(html.includes('符号报告版本不可识别'))
})
