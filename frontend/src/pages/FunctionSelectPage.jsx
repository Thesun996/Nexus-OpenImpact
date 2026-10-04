import { useState } from 'react';
import { useWorkflow } from '../state/WorkflowContext.jsx';
import { getSelectedSymbol } from '../state/workflow.js';
import { CoverageNotice, DiagnosticsList, EmptyWorkflow, ErrorNotice, ModeNotice, WorkflowSteps } from './PageParts.jsx';

export default function FunctionSelectPage({ navigate }) {
  const { state, actions } = useWorkflow();
  const [query, setQuery] = useState('');
  const busy = Object.values(state.loading).some(Boolean);
  const selected = getSelectedSymbol(state);
  const inspect = state.inspect;
  const symbols = inspect?.symbols || [];
  const visible = symbols.filter((symbol) => `${symbol.symbol_id} ${symbol.file}`.toLowerCase().includes(query.toLowerCase()));

  return (
    <>
      <section className="page-heading">
        <div><h1>选择分析函数</h1><p>从当前项目可解析的模块级函数中，选择计划修改的目标。</p></div>
        <div className="heading-actions"><span title={state.projectFingerprint || ''}>ZIP 指纹 <b>{state.projectFingerprint ? `${state.projectFingerprint.slice(0, 12)}…` : '尚未生成'}</b></span><button className="ghost-action" type="button" onClick={() => { actions.reset(); navigate('upload'); }}>重新开始</button><button className="ghost-action" type="button" disabled={!selected || busy} onClick={() => navigate('change')}>下一步</button></div>
      </section>
      <WorkflowSteps current={2} symbol={state.selectedSymbolId} /><ModeNotice mode={state.mode} /><ErrorNotice error={state.error} />
      {!inspect ? <EmptyWorkflow title={state.loading.inspect ? '正在读取项目' : '尚未读取项目'} message={state.loading.inspect ? '正在上传当前 ZIP 并获取函数列表，请等待请求结束。' : '请返回上传页选择 ZIP 并读取项目，或明确打开演示项目。当前没有可选择的函数。'} navigate={navigate} /> : <>
        <CoverageNotice coverage={inspect.coverage} />
        <section className="metric-grid project-summary-grid" aria-label="项目摘要">
          <article className="metric-card compact-metric"><div><span>项目名</span><strong>{inspect.project_name}</strong><p>{state.mode === 'demo' ? '固定演示项目' : '本次 ZIP 的 Inspect 结果'}</p></div><div className="metric-icon neutral">▣</div></article>
          <article className="metric-card compact-metric"><div><span>Python 文件</span><strong>{inspect.coverage?.python_files ?? inspect.modules?.length ?? '—'}</strong><p>{inspect.modules?.map((module) => module.module).join(' / ') || '没有模块'}</p></div><div className="metric-icon blue">▤</div></article>
          <article className="metric-card compact-metric"><div><span>函数数量</span><strong>{symbols.length}</strong><p>模块级函数</p></div><div className="metric-icon violet">‹/›</div></article>
          <article className="metric-card compact-metric"><div><span>覆盖状态</span><strong className={inspect.coverage?.status === 'complete' ? 'complete-label' : ''}>{inspect.coverage?.status || '未知'}</strong><p>{inspect.coverage?.status === 'complete' ? '在当前支持范围内完成解析' : '请检查诊断与分析边界'}</p></div><div className="metric-icon neutral">✓</div></article>
        </section>
        <section className="table-card workflow-table-card">
          <div className="tabs"><button className="active" type="button">函数列表</button></div>
          <div className="toolbar function-toolbar"><label className="filter-input"><span>⌕</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索函数或文件…" aria-label="搜索函数或文件" /></label><span>模块级函数</span><span>返回顺序</span></div>
          <div className="function-table" aria-label="函数列表">
            <div className="function-row table-head"><span>函数名</span><span>文件</span><span>行号</span><span>参数</span></div>
            {visible.map((symbol) => <button className={`function-row${symbol.symbol_id === state.selectedSymbolId ? ' selected' : ''}`} key={symbol.symbol_id} type="button" aria-pressed={symbol.symbol_id === state.selectedSymbolId} onClick={() => actions.selectSymbol(symbol.symbol_id)}><span className="symbol-name">{symbol.symbol_id}</span><span>{symbol.file}</span><span>{symbol.line}</span><span>{symbol.parameters?.length ? symbol.parameters.map((parameter) => <mark className="param-chip" key={parameter.name} title={`${parameter.kind} · ${parameter.has_default ? '可选参数' : '无默认值'}`}>{parameter.kind === 'var_positional' ? '*' : parameter.kind === 'var_keyword' ? '**' : ''}{parameter.name}{parameter.has_default ? ' = …' : ''}</mark>) : <span className="muted-cell">无参数</span>}</span></button>)}
            {!visible.length && <div className="state-message">{symbols.length ? '没有匹配的函数。' : '未发现可支持的模块级函数，请检查项目诊断。'}</div>}
          </div>
          <footer className="table-footer"><span>共 {symbols.length} 个函数</span><span>已选择 <b>{state.selectedSymbolId || '尚未选择'}</b></span><button className="primary-action" type="button" disabled={!selected || busy} onClick={() => navigate('change')}>配置变更</button></footer>
        </section>
        <article className="detail-card diagnostics-card"><header><div className="detail-title"><b>!</b> 解析诊断</div></header><section className="diagnostics-list"><DiagnosticsList diagnostics={inspect.diagnostics} /></section></article>
      </>}
    </>
  );
}
