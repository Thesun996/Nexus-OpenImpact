import { moduleDiagnosticEntries } from './moduleReportData.js';
import { getSelectedModule } from '../state/workflow.js';
import { MODULE_CHANGE_TYPES } from '../state/moduleDraft.js';
import { CoverageNotice, DiagnosticsList, EmptyWorkflow, ErrorNotice } from './PageParts.jsx';
import { WorkflowNotes } from '../components/workflow/WorkflowParts.jsx';

export default function ModuleChangeView({ state, onSelectChangeType, onUpdateChange, onValidate, onAnalyze, navigate }) {
  const selected = getSelectedModule(state);
  const { changeType, operation } = state.change;
  const rename = changeType === 'rename_module';
  const valid = state.validation?.validation?.valid === true;
  const busy = Object.values(state.loading).some(Boolean);
  const configured = rename ? Boolean(operation.newModuleName.trim()) : operation.confirmed === true;
  const spec = valid ? state.validation.change_spec : null;
  return <div className="oi-workflow-page oi-change-page">
    <section className="page-heading"><div><h1>配置模块变更</h1><p>拟定文件布局变化，校验后追踪真实静态导入；不改动源码。</p></div><button type="button" className="ghost-action" onClick={() => navigate('functions')}>返回选择</button></section>
    <WorkflowNotes current={3} mode={state.mode} /><ErrorNotice error={state.validation && state.error ? { ...state.error, diagnostics: undefined } : state.error} />
    {!selected ? <EmptyWorkflow title="尚未选择目标模块" message="先读取 ZIP，在模块领域选择受支持的根模块。" navigate={navigate} /> : <>
      <CoverageNotice coverage={state.validation?.coverage || state.inspect?.module_coverage} />
      <fieldset className="oi-change-type-selector"><legend>模块变更类型</legend><div className="oi-change-type-options">{MODULE_CHANGE_TYPES.map(type => <label className={`oi-change-type-option${changeType === type.value ? ' is-selected' : ''}`} key={type.value}>
        <input name="module-change-type" type="radio" aria-label={type.label} checked={changeType === type.value} onChange={() => onSelectChangeType(type.value)} /><span><b>{type.label}</b><small>{type.description}</small></span>
      </label>)}</div></fieldset>
      <section className="oi-change-workspace">
        <article className="oi-change-original"><h2>目标模块</h2><b>{selected.module_id}</b><p><code>{selected.file}</code></p><p>首版限定根目录普通模块与明确顶层绝对导入。</p></article>
        <article className="oi-change-input"><h2>{rename ? '拟定新模块名' : '拟定模块删除'}</h2><form className="oi-change-form" onSubmit={e => { e.preventDefault(); if (configured && !busy) onValidate(); }}>
          {rename ? <label><span>新模块名</span><input required autoComplete="off" value={operation.newModuleName} onChange={e => onUpdateChange({ newModuleName: e.target.value })} placeholder="Python 标识符，不含 .py 或路径" /><small>名称、大小写冲突和虚拟布局由后端最终校验。</small></label>
            : <label className="oi-delete-confirm"><input type="checkbox" checked={operation.confirmed === true} onChange={e => onUpdateChange({ confirmed: e.target.checked })} /><span>我确认分析拟定删除 {selected.file}；OpenImpact 不会删除或修改文件。</span></label>}
          <button className="primary-action" type="submit" disabled={!configured || busy}>{state.loading.validate ? '正在校验…' : '校验变更'}</button>
        </form></article>
        <article className="oi-change-result" aria-busy={busy}><header><h2>虚拟项目布局</h2><span className={`oi-validation-status${valid ? ' is-valid' : ''}`} role="status">{state.loading.validate ? '校验中' : valid ? '已确认变更 · 后端校验通过' : state.validation ? '校验未通过' : '模块草稿 · 待校验'}</span></header>
          <div className="oi-signature-before"><span className="oi-field-caption">变更前</span><code>{spec?.before.file || selected.file}</code></div>
          <div className="oi-signature-after"><span className="oi-field-caption">{valid ? '变更后 · 后端已校验' : '草稿布局 · 待校验'}</span><code>{valid ? spec.after?.file || '模块不再位于项目布局中' : rename ? operation.newModuleName.trim() ? `${operation.newModuleName.trim()}.py` : '待填写新名称' : '拟定删除当前模块'}</code></div>
          <p>仅比较虚拟布局中的导入绑定。上游依赖建议检查，不代表确定运行失败。</p>
          {state.validation && <section className="oi-validation-diagnostics"><DiagnosticsList diagnostics={state.validation.validation?.diagnostics} showEmptyState={false} /><DiagnosticsList diagnostics={moduleDiagnosticEntries(state.validation.diagnostics)} showEmptyState={false} /></section>}
          <footer className="oi-change-actions"><span>继续使用当前原始 ZIP 与项目指纹。</span><button className="primary-action" type="button" disabled={!valid || busy} onClick={onAnalyze}>{state.loading.analyze ? '正在分析…' : '开始分析'}</button></footer>
        </article>
      </section>
    </>}
  </div>;
}
