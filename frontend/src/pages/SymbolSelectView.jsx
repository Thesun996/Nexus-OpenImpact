import { reasonLabel } from '../presentation/labels.js';
import { getSelectedVariableSymbol } from '../state/workflow.js';
import { CoverageNotice, DiagnosticsList, EmptyWorkflow, ErrorNotice } from './PageParts.jsx';
import DomainSelector from '../components/workflow/DomainSelector.jsx';
import { symbolDiagnosticEntries, SYMBOL_REASONS } from './symbolReportData.js';

export default function SymbolSelectView({ state, query, onQueryChange, onSelectModule, onSelectVariableSymbol, onSelectDomain, onReset, navigate }) {
  const selected = getSelectedVariableSymbol(state);
  const modules = state.inspect?.module_inventory?.modules || [];
  const symbols = (state.inspect?.symbol_inventory?.symbols || []).filter(s => s.module_id === state.selectedModuleId && `${s.symbol_id} ${s.file}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="oi-workflow-page oi-functions-page">
    <section className="page-heading"><div><h1>选择模块符号</h1><p>先确认模块，再选择本次源码中的公开变量或常量。</p></div><button className="ghost-action" onClick={onReset}>重新开始</button></section>
    <DomainSelector domain="symbol" mode={state.mode} onSelect={onSelectDomain} /><ErrorNotice error={state.error} />
    {!state.inspect ? <EmptyWorkflow title="尚未读取项目" message="请先上传原始 Python ZIP。" navigate={navigate} /> : <>
      <CoverageNotice coverage={state.inspect.symbol_coverage} />
      <fieldset className="oi-operation-parameters"><legend>选择所属模块</legend><div className="oi-symbol-module-options">{modules.map(module => <label className={`oi-operation-parameter${module.module_id === state.selectedModuleId ? ' is-selected' : ''}`} key={module.file}>
        <input type="radio" name="symbol-module" aria-label={`符号模块 ${module.module_id}`} disabled={!module.selectable} checked={module.module_id === state.selectedModuleId} onChange={() => onSelectModule(module.module_id)} /><span><code>{module.file}</code><small>{module.selectable ? '根模块' : `不可选：${reasonLabel(module.reason)}`}</small></span>
      </label>)}</div></fieldset>
      <div className="oi-symbol-workspace"><section className="oi-symbol-index" aria-label="公开变量与常量列表"><header><h2>模块级变量 / 常量</h2><span>{symbols.length} 条</span></header>
        <label className="oi-symbol-search"><span>搜索符号或文件</span><input type="search" value={query} onChange={e => onQueryChange(e.target.value)} /></label>
        <div className="oi-symbol-rows">{symbols.map(symbol => <button type="button" className={`oi-symbol-row${selected?.symbol_id === symbol.symbol_id ? ' is-selected' : ''}`} key={symbol.symbol_id} disabled={!symbol.selectable} aria-pressed={selected?.symbol_id === symbol.symbol_id} onClick={() => onSelectVariableSymbol(symbol.symbol_id)}>
          <span className="oi-symbol-location">{symbol.file}:{symbol.line}</span><b>{symbol.symbol_id}</b><code>{symbol.definition}</code><span>{symbol.selectable ? `${symbol.kind === 'constant' ? '常量' : '变量'} · ${selected?.symbol_id === symbol.symbol_id ? '已选择' : '可选择'}` : `不支持：${SYMBOL_REASONS[symbol.reason] || reasonLabel(symbol.reason)}`}</span>
        </button>)}{!symbols.length && <p className="oi-symbol-empty">{state.selectedModuleId ? '当前模块没有匹配的变量或常量；查看诊断或更换模块。' : '请先选择模块。'}</p>}</div>
        <footer className="oi-symbol-actions"><span>{selected?.symbol_id || '请选择受支持定义'}</span><button className="primary-action" disabled={!selected || Object.values(state.loading).some(Boolean)} onClick={() => navigate('change')}>配置变更</button></footer>
      </section><aside className="oi-symbol-preview"><h2>原始定义</h2>{selected ? <><b>{selected.symbol_id}</b><p><code>{selected.file}:{selected.line}</code></p><pre className="code-block"><code>{selected.definition}</code></pre><p>仅分析拟定变更，不修改源码。</p></> : <p>禁用候选保留原因说明；后端校验为最终依据。</p>}</aside></div>
      <details className="oi-review-section"><summary>符号解析边界与诊断</summary><DiagnosticsList diagnostics={symbolDiagnosticEntries(state.inspect.symbol_diagnostics)} /></details>
    </>}
  </div>;
}
