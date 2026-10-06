import DomainSelector from '../components/workflow/DomainSelector.jsx';
import ModuleSelectView from './ModuleSelectView.jsx';
import SymbolSelectView from './SymbolSelectView.jsx';
import { useState } from 'react';
import { useWorkflow } from '../state/WorkflowContext.jsx';
import { getSelectedSymbol } from '../state/workflow.js';
import { CoverageNotice, EmptyWorkflow, ErrorNotice } from './PageParts.jsx';
import { ProjectDiagnostics, ProjectOverview, SignatureText, WorkflowNotes } from '../components/workflow/WorkflowParts.jsx';

export function FunctionSelectView({ state, query, onQueryChange, onSelect, onSelectDomain, onReset, navigate }) {
  const busy = Object.values(state.loading).some(Boolean);
  const selected = getSelectedSymbol(state);
  const inspect = state.inspect;
  const symbols = inspect?.symbols || [];
  const visible = symbols.filter((symbol) => `${symbol.symbol_id} ${symbol.file}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="oi-workflow-page oi-functions-page">
    <section className="page-heading"><div><h1>选择分析函数</h1><p>用完整函数标识 确认目标，再核对它的文件与原始签名。</p></div><div className="heading-actions"><button className="ghost-action" type="button" onClick={onReset}>重新开始</button></div></section>
    <DomainSelector domain="function" mode={state.mode} onSelect={onSelectDomain} />
    <WorkflowNotes current={2} mode={state.mode} /><ErrorNotice error={state.error} />
    {!inspect ? <EmptyWorkflow title={state.loading.inspect ? '正在读取项目' : '尚未读取项目'} message={state.loading.inspect ? '正在上传当前 ZIP 并获取函数列表，请等待请求结束。' : '请返回上传页选择 ZIP 并读取项目，或明确打开演示项目。当前没有可选择的函数。'} navigate={navigate} /> : <>
      <CoverageNotice coverage={inspect.coverage} /><ProjectOverview inspect={inspect} file={state.file} fingerprint={state.projectFingerprint} mode={state.mode} />
      <div className="oi-symbol-workspace">
        <section className="oi-symbol-index" aria-label="函数列表">
          <header><h2>模块级函数</h2><span>{visible.length} / {symbols.length} 条</span></header>
          <label className="oi-symbol-search"><span>搜索函数或文件</span><input type="search" value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="完整函数标识 或相对文件路径" /></label>
          <div className="oi-symbol-rows">
            {visible.map((symbol) => {
              const isSelected = symbol.symbol_id === state.selectedSymbolId;
              return <div className={`oi-symbol-row oi-function-row${isSelected ? ' is-selected' : ''}`} key={symbol.symbol_id}>
                <button className="oi-function-select" type="button" aria-pressed={isSelected} onClick={() => onSelect(symbol.symbol_id)}>
                  <span className="oi-symbol-location">{symbol.file}:{symbol.line}</span><b>{symbol.symbol_id}</b>
                  <span className="oi-symbol-signature"><SignatureText definition={symbol} /></span>
                  {!isSelected && <span className="oi-symbol-selection">选择此函数</span>}
                </button>
                {isSelected && <button className="primary-action oi-symbol-configure" type="button" disabled={busy} onClick={() => navigate('change')}>配置变更</button>}
              </div>;
            })}
            {!visible.length && <div className="oi-symbol-empty" role="status"><h3>{symbols.length ? '没有匹配的函数' : '未发现可支持的模块级函数'}</h3><p>{symbols.length ? '调整完整函数标识 或文件名，列表只筛选本次读取返回的函数。' : '请查看解析诊断，确认 ZIP 中包含模块级函数。当前不能继续配置变更。'}</p><button className="ghost-action" type="button" onClick={symbols.length ? () => onQueryChange('') : () => navigate('upload')}>{symbols.length ? '清空搜索' : '返回上传项目'}</button></div>}
          </div>
          <footer className="oi-symbol-actions"><span>{selected ? `已选择 ${selected.symbol_id}` : '请选择一个函数'}</span>{!visible.some(symbol => symbol.symbol_id === selected?.symbol_id) && <button className="primary-action" type="button" disabled={!selected || busy} onClick={() => navigate('change')}>配置变更</button>}</footer>
        </section>
        <aside className={`oi-symbol-preview${selected ? ' has-selection' : ''}`} aria-label="当前选择"><h2>当前选择</h2>{selected ? <><b>{selected.symbol_id}</b><p><code>{selected.file}:{selected.line}</code></p><span className="oi-field-caption">原始签名</span><SignatureText definition={selected} /><p>来自本次读取的结构化参数。修改后签名将在下一步交由后端校验。</p></> : <p>选择列表中的完整函数标识，查看原始签名。不同模块中的同名函数分别保留。</p>}</aside>
      </div>
      <ProjectDiagnostics diagnostics={inspect.diagnostics} coverage={inspect.coverage} />
    </>}
  </div>;
}

export default function FunctionSelectPage({ navigate }) {
  const { state, actions } = useWorkflow();
  const [query, setQuery] = useState('');
  const View = state.changeDomain === 'symbol' ? SymbolSelectView : state.changeDomain === 'module' ? ModuleSelectView : FunctionSelectView;
  return <View state={state} query={query} onQueryChange={setQuery} onSelectModule={actions.selectModule} onSelectVariableSymbol={actions.selectVariableSymbol} onSelect={state.changeDomain === 'module' ? actions.selectModule : actions.selectSymbol} onSelectDomain={actions.selectDomain} onReset={() => { actions.reset(); navigate('upload'); }} navigate={navigate} />;
}
