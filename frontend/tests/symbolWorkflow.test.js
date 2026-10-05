import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createInitialState, workflowReducer, buildChangePayload } from '../src/state/workflow.js'
import { createWorkflowActions } from '../src/state/actions.js'
import { createSymbolDraft, updateSymbolDraft, buildSymbolPayload } from '../src/state/symbolDraft.js'
import { symbolFindings, symbolEvidence, symbolExplanation } from '../src/pages/symbolReportData.js'
const fixture = JSON.parse(readFileSync(new URL('./fixtures/symbol-responses.json', import.meta.url)))
const original = new File(['actual bytes'], 'symbols.zip')
function harness(overrides = {}) {
  let state = createInitialState(); const calls = []
  const client = {
    inspect: async (...args) => { calls.push(['inspect',...args]); return structuredClone(fixture.inspect) },
    validate: async (...args) => { calls.push(['validate',...args]); return structuredClone(fixture.validation) },
    analyze: async (...args) => { calls.push(['analyze',...args]); return structuredClone(fixture.report) }, ...overrides,
  }
  const actions = createWorkflowActions({ getState: () => state, dispatch: a => { state = workflowReducer(state,a) }, client })
  return { actions, calls, state: () => state }
}
async function ready(h) {
  h.actions.selectFile(original); assert.equal(await h.actions.inspectProject(),true)
  h.actions.selectDomain('symbol'); h.actions.selectModule('config'); h.actions.selectVariableSymbol('config.MAX_RETRIES'); h.actions.updateChange({ newSymbolName:'RETRY_LIMIT' })
}
test('precise symbol payloads never manufacture signatures or submit deletion confirmation', () => {
  const draft = updateSymbolDraft(createSymbolDraft(), { newSymbolName:' RETRY_LIMIT ', parameterName:'bad' })
  assert.deepEqual(buildSymbolPayload('config.MAX_RETRIES',draft),{change_domain:'symbol',change_type:'rename_module_symbol',target_symbol_id:'config.MAX_RETRIES',new_symbol_name:'RETRY_LIMIT'})
  assert.deepEqual(updateSymbolDraft(createSymbolDraft('remove_module_symbol'),{confirmed:true,newSymbolName:'bad'}).operation,{confirmed:true})
})
test('symbol flow resubmits identical File and Inspect fingerprint and stores independent report', async () => {
  const h = harness(); await ready(h)
  assert.equal(await h.actions.validateChange(),true); assert.equal(await h.actions.analyzeProject(),true)
  assert.equal(h.state().report.report_kind,'symbol_impact')
  h.calls.forEach(call => assert.equal(call[1],original))
  h.calls.slice(1).forEach(call => assert.equal(call[3],fixture.inspect.project_fingerprint))
})
test('third domain invalidates both old domains and preserves original upload', async () => {
  const h = harness(); await ready(h); await h.actions.validateChange(); await h.actions.analyzeProject()
  for (const domain of ['module','function','symbol']) {
    const revision = h.state().revision; h.actions.selectDomain(domain)
    assert.equal(h.state().revision,revision+1); assert.equal(h.state().selectedVariableSymbolId,null)
    assert.equal(h.state().validation,null); assert.equal(h.state().report,null); assert.equal(h.state().file,original)
  }
})
test('disabled candidates and cross-module symbols cannot become targets', async () => {
  const inspect = structuredClone(fixture.inspect); inspect.symbol_inventory.symbols[0].selectable=false
  const h = harness({inspect:async()=>inspect}); await ready(h); assert.equal(h.state().selectedVariableSymbolId,null)
  h.actions.selectVariableSymbol('other.MAX_RETRIES'); assert.equal(h.state().selectedVariableSymbolId,null)
})
test('deletion requires confirmation; type, target and module selection clear old operation fields', async () => {
  const h = harness(); await ready(h); h.actions.selectChangeType('remove_module_symbol')
  assert.equal(await h.actions.validateChange(),false); assert.equal(h.state().error.code,'confirmation_required')
  h.actions.updateChange({confirmed:true}); assert.deepEqual(buildChangePayload(h.state()),{change_domain:'symbol',change_type:'remove_module_symbol',target_symbol_id:'config.MAX_RETRIES'})
  h.actions.selectModule('config'); assert.equal(h.state().selectedVariableSymbolId,null); assert.deepEqual(h.state().change.operation,{confirmed:false})
})
for (const stage of ['validate','analyze']) {
  test(`late symbol ${stage} cannot cross a domain switch`, async () => {
    let resolve,signal; const h=harness({[stage]:(_f,_c,_p,options)=>{signal=options.signal; return new Promise(r=>{resolve=r})}})
    await ready(h); if(stage==='analyze') await h.actions.validateChange()
    const promise=stage==='validate'?h.actions.validateChange():h.actions.analyzeProject(); h.actions.selectDomain('module')
    assert.equal(signal.aborted,true); resolve(structuredClone(stage==='validate'?fixture.validation:fixture.report))
    assert.equal(await promise,false); assert.equal(h.state().validation,null); assert.equal(h.state().report,null)
  })
}
for (const tamper of [v=>{v.change_spec.before.source_hash='f'.repeat(64)},v=>{v.change_spec.after.value_source='42'},v=>{v.change_spec.modifies_source=true}]) {
  test(`symbol validation rejects canonical snapshot tampering ${tamper}`, async()=>{
    const response=structuredClone(fixture.validation); tamper(response)
    const h=harness({validate:async()=>response}); await ready(h)
    assert.equal(await h.actions.validateChange(),false); assert.equal(h.state().error.code,'invalid_response')
  })
}
test('symbol Analyze checks fingerprint even on successful HTTP transport',async()=>{
  const report=structuredClone(fixture.report); report.project_fingerprint='0'.repeat(64)
  const h=harness({analyze:async()=>report}); await ready(h); await h.actions.validateChange()
  assert.equal(await h.actions.analyzeProject(),false); assert.equal(h.state().error.code,'fingerprint_mismatch'); assert.equal(h.state().file,original)
})
test('symbol evidence matches actual reference and terminal seed independently of same names',()=>{
  const report=structuredClone(fixture.report)
  symbolFindings(report).forEach((finding,index)=>{const evidence=symbolEvidence(report,index,finding); assert.ok(evidence); assert.ok(symbolExplanation(report,index,evidence))})
  for(const tamper of [e=>{e.evidence_reference='bad'},e=>{e.before_resolution.expression='other'},e=>{e.target_symbol_id='other.MAX_RETRIES'}]){
    const data=structuredClone(fixture.report); tamper(data.evidences[0]); assert.equal(symbolEvidence(data,0,symbolFindings(data)[0]),null)
  }
})
test('unrelated propagation terminal or seed and reordered explanations become unavailable',()=>{
  for(const tamper of [e=>{e.propagation_path[0].modules[0]='fake'},e=>{e.propagation_path[0].terminal_reference.expression='fake'},e=>{e.propagation_path[0].source_direct_impact='fake'}]){
    const data=structuredClone(fixture.report); tamper(data.evidences[1]); assert.equal(symbolEvidence(data,1,symbolFindings(data)[1]),null)
  }
  const data=structuredClone(fixture.report); data.explanations[0].evidence_reference='fake'; assert.equal(symbolExplanation(data,0,data.evidences[0]),null)
})
test('unavailable evidence retains finding but cannot borrow an explanation',()=>{
  const data=structuredClone(fixture.report); data.evidences[0].status='unavailable'
  const evidence=symbolEvidence(data,0,symbolFindings(data)[0]); assert.ok(evidence); assert.equal(symbolExplanation(data,0,evidence),null)
})
