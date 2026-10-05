import { getSelectedVariableSymbol } from '../state/workflow.js';
import { SYMBOL_CHANGE_TYPES } from '../state/symbolDraft.js';
import { CoverageNotice, DiagnosticsList, EmptyWorkflow, ErrorNotice } from './PageParts.jsx';
import { symbolDiagnosticEntries } from './symbolReportData.js';

export default function SymbolChangeView({ state, onSelectChangeType, onUpdateChange, onValidate, onAnalyze, navigate }) {
  const selected = getSelectedVariableSymbol(state), { changeType, operation } = state.change;
  const rename = changeType === 'rename_module_symbol', valid = state.validation?.validation?.valid === true;
  const busy = Object.values(state.loading).some(Boolean), configured = rename ? Boolean(operation.newSymbolName.trim()) : operation.confirmed === true;
  const spec = valid ? state.validation.change_spec : null;
  const draft = rename ? operation.newSymbolName.trim() ? `${operation.newSymbolName.trim()}${selected?.annotation_source ? `: ${selected.annotation_source}` : ''} = ${selected?.value_source}` : '待填写新名称' : '拟定移除当前定义';
  return <div className="oi-workflow-page oi-change-page">
    <section className="page-heading"><div><h1>配置符号变更</h1><p>拟定变量或常量名称变化，追踪真实静态引用。</p></div><button className="ghost-action" onClick={() => navigate('functions')}>返回选择</button></section>
    <ErrorNotice error={state.validation && state.error ? { ...state.error, diagnostics: undefined } : state.error} />
    {!selected ? <EmptyWorkflow title="尚未选择模块符号" message="请先从当前 ZIP 选择受支持的公开定义。" navigate={navigate} /> : <>
      <CoverageNotice coverage={state.validation?.coverage || state.inspect.symbol_coverage} />
      <fieldset className="oi-change-type-selector"><legend>符号变更类型</legend><div className="oi-change-type-options">{SYMBOL_CHANGE_TYPES.map(type => <label className={`oi-change-type-option${type.value === changeType ? ' is-selected' : ''}`} key={type.value}><input name="symbol-change-type" aria-label={type.label} type="radio" checked={type.value === changeType} onChange={() => onSelectChangeType(type.value)} /><span><b>{type.label}</b><small>{type.description}</small></span></label>)}</div></fieldset>
      <section className="oi-change-workspace"><article className="oi-change-original"><h2>目标定义</h2><b>{selected.symbol_id}</b><p><code>{selected.file}:{selected.line}</code></p><pre className="code-block"><code>{selected.definition}</code></pre></article>
        <article className="oi-change-input"><h2>{rename ? '拟定新符号名' : '拟定删除定义'}</h2><form className="oi-change-form" onSubmit={event => { event.preventDefault(); if (configured && !busy) onValidate(); }}>
          {rename ? <label><span>新符号名</span><input required autoComplete="off" value={operation.newSymbolName} onChange={e => onUpdateChange({ newSymbolName: e.target.value })} /><small>公开标识符、名称冲突与定义快照由后端最终校验。</small></label>
            : <label className="oi-delete-confirm"><input type="checkbox" checked={operation.confirmed === true} onChange={e => onUpdateChange({ confirmed: e.target.checked })} /><span>我确认仅分析拟定删除 {selected.name}；OpenImpact 不修改或删除上传文件。</span></label>}
          <button className="primary-action" disabled={!configured || busy} type="submit">{state.loading.validate ? '正在校验…' : '校验变更'}</button>
        </form></article>
        <article className="oi-change-result"><header><h2>定义变化</h2><span className={`oi-validation-status${valid ? ' is-valid' : ''}`} role="status">{state.loading.validate ? '校验中' : valid ? '已确认变更 · 后端校验通过' : state.validation ? '校验未通过' : '符号草稿 · 待校验'}</span></header>
          <div className="oi-signature-before"><span className="oi-field-caption">变更前</span><code>{spec?.before.definition || selected.definition}</code></div><div className="oi-signature-after"><span className="oi-field-caption">{valid ? '变更后 · 后端已校验' : '草稿 · 待校验'}</span><code>{valid ? spec.after?.definition || '定义不再提供旧名称' : draft}</code></div>
          <p>直接影响只代表新产生的确定静态引用断裂；不保证运行时失败。</p>
          {state.validation && <section className="oi-validation-diagnostics"><DiagnosticsList diagnostics={state.validation.validation?.diagnostics} showEmptyState={false} /><DiagnosticsList diagnostics={symbolDiagnosticEntries(state.validation.diagnostics)} showEmptyState={false} /></section>}
          <footer className="oi-change-actions"><span>重复提交同一原始 ZIP 与指纹。</span><button className="primary-action" disabled={!valid || busy} onClick={onAnalyze}>{state.loading.analyze ? '正在分析…' : '开始分析'}</button></footer>
        </article>
      </section>
    </>}
  </div>;
}
