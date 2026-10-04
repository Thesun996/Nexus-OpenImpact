import { useWorkflow } from '../state/WorkflowContext.jsx';
import { getSelectedSymbol } from '../state/workflow.js';
import { CoverageNotice, DiagnosticsList, EmptyWorkflow, ErrorNotice } from './PageParts.jsx';
import { diagnosticCount, SignatureText, WorkflowNotes } from '../components/workflow/WorkflowParts.jsx';

export function ChangeView({ state, onUpdateChange, onValidate, onAnalyze, navigate }) {
  const selected = getSelectedSymbol(state);
  const validation = state.validation;
  const valid = validation?.validation?.valid === true;
  const busy = Object.values(state.loading).some(Boolean);
  const validationDiagnostics = diagnosticCount(validation?.validation?.diagnostics);
  const projectDiagnostics = diagnosticCount(validation?.diagnostics);
  return <div className="oi-workflow-page oi-change-page">
    <section className="page-heading"><div><h1>配置签名变更</h1><p>新增一个必填参数，核对计划签名，再分析调用影响。</p></div><div className="heading-actions"><button className="ghost-action" type="button" onClick={() => navigate('functions')}>返回选择</button></div></section>
    <WorkflowNotes current={3} mode={state.mode} /><ErrorNotice error={state.error} />
    {!selected ? <EmptyWorkflow title="尚未选择目标函数" message="请先读取项目并选择一个模块级函数。" navigate={navigate} /> : <>
      <CoverageNotice coverage={state.inspect?.coverage} />
      <section className="oi-change-workspace">
        <article className="oi-change-original" aria-label="目标函数与原始签名"><h2>目标函数</h2><b>{selected.symbol_id}</b><p><code>{selected.file}:{selected.line}</code></p><span className="oi-field-caption">原始签名</span><SignatureText definition={selected} /><p>此处只读取源码。计划变更不会修改上传项目。</p></article>
        <article className="oi-change-input" aria-label="新增必填参数"><header><h2>新增必填参数</h2><span className="oi-change-mark">+ 参数</span></header>
          <form className="oi-change-form" aria-busy={state.loading.validate} onSubmit={(event) => { event.preventDefault(); onValidate(); }}>
            <label><span>新增参数名</span><input type="text" value={state.change.parameterName} onChange={(event) => onUpdateChange({ parameterName: event.target.value })} placeholder="填写 Python 参数名" required autoComplete="off" /></label>
            <label><span>参数类型</span><select aria-label="参数类型" value={state.change.parameterKind} onChange={(event) => onUpdateChange({ parameterKind: event.target.value })}><option value="positional_or_keyword">普通位置或关键字参数</option><option value="positional_only">仅位置参数</option><option value="keyword_only">仅关键字参数</option></select><small><code>{state.change.parameterKind}</code></small></label>
            <label><span>插入位置（可选）</span><select aria-label="插入位置（可选）" aria-describedby="oi-insertion-help" value={state.change.insertBefore} onChange={(event) => onUpdateChange({ insertBefore: event.target.value })}><option value="">使用后端默认位置</option>{selected.parameters?.map((parameter) => <option value={parameter.name} key={parameter.name}>放在 {parameter.name} 前</option>)}</select><small id="oi-insertion-help">对应 insert_before。参数位置与合法性由后端判断。</small></label>
            {state.mode === 'demo' && <p className="oi-demo-warning">演示仅接受固定案例配置，其他配置会明确拒绝。</p>}
            <button className="primary-action" type="submit" disabled={!state.change.parameterName.trim() || busy}>{state.loading.validate ? '正在校验…' : '校验变更'}</button>
          </form>
        </article>
        <article className="oi-change-result" aria-label="计划签名与校验结果" aria-busy={state.loading.validate || state.loading.analyze}>
          <header><h2>计划签名</h2><span className={`oi-validation-status${valid ? ' is-valid' : validation ? ' is-invalid' : ''}`} role="status">{state.loading.validate ? '校验中' : validation ? valid ? '校验通过' : '校验未通过' : '参数草稿 · 尚未校验'}</span></header>
          <div className="oi-signature-before"><span className="oi-field-caption">修改前</span><SignatureText definition={validation?.change_spec?.before || selected} /></div>
          <div className="oi-signature-after"><span className="oi-field-caption">{valid ? '修改后 · 后端已校验' : validation?.change_spec?.after ? '后端候选签名 · 未通过' : '修改后签名待后端校验'}</span>{validation?.change_spec?.after ? <SignatureText definition={validation.change_spec.after} addedParameterName={valid ? validation.change_spec.added_parameter?.name : undefined} /> : <div className="oi-parameter-draft"><span>+ {state.change.parameterName || '待填写参数'}</span><small>{state.change.parameterKind} · 必填</small><p>草稿只记录参数配置，尚未生成有效目标签名。</p></div>}</div>
          <p className="oi-validation-message">{state.loading.validate ? '正在使用当前 ZIP 与 Inspect 指纹构建并校验 ChangeSpec。' : valid ? state.mode === 'demo' ? '演示 ChangeSpec 已匹配固定案例，可查看演示报告。' : 'ChangeSpec 校验通过，可以提交分析。' : validation ? '当前配置未通过后端校验，请根据诊断调整参数后重新校验。' : '修改输入后，旧校验与报告立即失效；需重新校验。'}</p>
          {validation && (validationDiagnostics > 0 || projectDiagnostics > 0 || validation.coverage?.status === 'partial') && <section className="oi-validation-diagnostics" aria-label="后端校验诊断">{validationDiagnostics > 0 && <DiagnosticsList diagnostics={validation.validation?.diagnostics} />}<CoverageNotice coverage={validation.coverage} />{projectDiagnostics > 0 && <DiagnosticsList diagnostics={validation.diagnostics} />}</section>}
          <footer className="oi-change-actions"><span>{state.mode === 'demo' ? '下一步展示独立演示结果' : '分析继续使用本次原始 ZIP 与 Inspect 指纹。'}</span><button className="primary-action" type="button" onClick={onAnalyze} disabled={!valid || busy}>{state.loading.analyze ? '正在分析…' : state.mode === 'demo' ? '查看演示报告' : '开始分析'}</button></footer>
        </article>
      </section>
    </>}
  </div>;
}

export default function ChangePage({ navigate }) {
  const { state, actions } = useWorkflow();
  async function analyze() { if (await actions.analyzeProject()) navigate('report'); }
  return <ChangeView state={state} onUpdateChange={actions.updateChange} onValidate={() => { void actions.validateChange(); }} onAnalyze={analyze} navigate={navigate} />;
}
