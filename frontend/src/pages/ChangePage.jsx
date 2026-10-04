import { useWorkflow } from '../state/WorkflowContext.jsx';
import { formatSignature, getSelectedSymbol } from '../state/workflow.js';
import { CoverageNotice, DiagnosticsList, EmptyWorkflow, ErrorNotice, ModeNotice, WorkflowSteps } from './PageParts.jsx';

export default function ChangePage({ navigate }) {
  const { state, actions } = useWorkflow();
  const selected = getSelectedSymbol(state);
  const validation = state.validation;
  const valid = validation?.validation?.valid === true;
  const busy = Object.values(state.loading).some(Boolean);

  async function analyze() {
    if (await actions.analyzeProject()) navigate('report');
  }

  return (
    <>
      <section className="page-heading"><div><h1>配置签名变更</h1><p>填写新增必填参数，先校验结构化 ChangeSpec，再查看分析结果。</p></div><div className="heading-actions"><span>目标 <b>{state.selectedSymbolId || '尚未选择'}</b></span><button className="ghost-action" type="button" onClick={() => navigate('functions')}>返回选择</button></div></section>
      <WorkflowSteps current={3} symbol={state.selectedSymbolId} /><ModeNotice mode={state.mode} /><ErrorNotice error={state.error} />
      {!selected ? <EmptyWorkflow title="尚未选择目标函数" message="请先读取项目并选择一个模块级函数。" navigate={navigate} /> : <>
        <CoverageNotice coverage={state.inspect?.coverage} />
        <section className="config-grid">
          <article className="detail-card target-card"><header><div className="detail-title"><b>‹/›</b> 目标函数</div></header><section className="info-list signature-info"><div><span>目标函数</span><b>{selected.symbol_id}</b></div><div><span>当前签名</span><code>{formatSignature(selected)}</code></div><div><span>文件位置</span><b>{selected.file}:{selected.line}</b></div><div><span>覆盖状态</span><mark className={`tag ${state.inspect?.coverage?.status === 'complete' ? 'low' : 'medium'}`}>{state.inspect?.coverage?.status || '未知'}</mark></div></section></article>
          <article className="detail-card form-card"><header><div className="detail-title"><b>＋</b> 新增必填参数</div></header>
            <form className="change-form" onSubmit={(event) => { event.preventDefault(); void actions.validateChange(); }}>
              <label><span>新增参数名</span><input type="text" value={state.change.parameterName} onChange={(event) => actions.updateChange({ parameterName: event.target.value })} placeholder="例如 timezone" required autoComplete="off" /></label>
              <label><span>参数类型</span><select value={state.change.parameterKind} onChange={(event) => actions.updateChange({ parameterKind: event.target.value })}><option value="positional_or_keyword">positional_or_keyword</option><option value="positional_only">positional_only</option><option value="keyword_only">keyword_only</option></select></label>
              <label><span>insert_before（可选）</span><select value={state.change.insertBefore} onChange={(event) => actions.updateChange({ insertBefore: event.target.value })}><option value="">使用后端默认位置</option>{selected.parameters?.map((parameter) => <option value={parameter.name} key={parameter.name}>放在 {parameter.name} 前</option>)}</select></label>
              <small>{state.mode === 'demo' ? '演示只接受固定参数配置，其他配置会明确拒绝。' : '当前签名来自本次 ZIP。新增参数位置和新签名合法性由后端校验，前端不会猜测插入位置。'}</small>
              <button className="primary-action form-submit" type="submit" disabled={!state.change.parameterName.trim() || busy}>{state.loading.validate ? '正在校验…' : '校验变更'}</button>
            </form>
          </article>
          <article className="detail-card validation-card"><header><div className="detail-title"><b>✓</b> 校验结果</div><mark className={`tag ${valid ? 'low' : 'medium'}`}>{state.loading.validate ? '校验中' : validation ? valid ? '校验通过' : '校验未通过' : '尚未校验'}</mark></header>
            <section className="signature-compare"><div><span>修改前</span><code>{formatSignature(validation?.change_spec?.before || selected)}</code></div><div><span>修改后</span><code>{validation?.change_spec?.after ? formatSignature(validation.change_spec.after) : '等待合法 ChangeSpec'}</code></div></section>
            <section className="state-message">{state.loading.validate ? '正在使用当前 ZIP 与 Inspect 指纹构建并校验 ChangeSpec。' : valid ? state.mode === 'demo' ? '演示 ChangeSpec 已匹配固定案例，可查看演示报告。' : 'ChangeSpec 校验通过，可以提交分析。' : validation ? '当前配置未通过后端校验，请根据诊断调整参数后重新校验。' : '请校验当前配置。更换参数或目标会清除旧校验结果与报告。'}</section>
            {validation && <section className="diagnostics-list"><DiagnosticsList diagnostics={validation.validation?.diagnostics} /></section>}
            {validation && <section className="diagnostics-list"><CoverageNotice coverage={validation.coverage} /><DiagnosticsList diagnostics={validation.diagnostics} /></section>}
            <footer className="config-actions"><span>{state.mode === 'demo' ? '下一步展示独立演示结果' : '使用同一原始 ZIP 与 project_fingerprint 提交分析'}</span><button className="primary-action" type="button" onClick={analyze} disabled={!valid || busy}>{state.loading.analyze ? '正在分析…' : state.mode === 'demo' ? '查看演示报告' : '开始分析'}</button></footer>
          </article>
        </section>
      </>}
    </>
  );
}
