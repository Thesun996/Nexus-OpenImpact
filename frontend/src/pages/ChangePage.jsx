import ModuleChangeView from './ModuleChangeView.jsx';
import SymbolChangeView from './SymbolChangeView.jsx';
import { useWorkflow } from '../state/WorkflowContext.jsx';
import { getSelectedSymbol } from '../state/workflow.js';
import { CHANGE_TYPES, describeChange, getParameterChoices, previewSignature } from '../state/changeDraft.js';
import { CoverageNotice, DiagnosticsList, EmptyWorkflow, ErrorNotice } from './PageParts.jsx';
import { diagnosticCount, SignatureText, WorkflowNotes } from '../components/workflow/WorkflowParts.jsx';

const KIND_LABELS = {
  positional_only: '仅位置参数', positional_or_keyword: '普通位置或关键字参数',
  keyword_only: '仅关键字参数', var_positional: '可变位置参数', var_keyword: '可变关键字参数',
};

function ChangeTypeSelector({ changeType, mode, onSelect }) {
  return <fieldset className="oi-change-type-selector"><legend>变更类型</legend>
    <div className="oi-change-type-options">{CHANGE_TYPES.map((type) => {
      const unavailable = mode === 'demo' && type.value !== 'add_required_parameter';
      return <label className={`oi-change-type-option${type.value === changeType ? ' is-selected' : ''}${unavailable ? ' is-disabled' : ''}`} key={type.value}>
        <input type="radio" name="change-type" aria-label={type.label} value={type.value} checked={type.value === changeType} disabled={unavailable} onChange={() => onSelect(type.value)} />
        <span><b>{type.label}</b><small>{unavailable ? '请上传实际项目使用此类型' : type.description}</small></span>
      </label>;
    })}</div>
  </fieldset>;
}

function ParameterSelector({ choices, selectedName, onSelect }) {
  return <fieldset className="oi-operation-parameters"><legend>选择现有参数</legend>
    {choices.length === 0 ? <p className="oi-parameter-empty">此函数没有参数。可切换为新增参数，或返回选择其他函数。</p>
      : choices.map(({ parameter, enabled, reason }, index) => <label className={`oi-operation-parameter${parameter.name === selectedName ? ' is-selected' : ''}${enabled ? '' : ' is-disabled'}`} key={parameter.name}>
        <input type="radio" name="operation-parameter" aria-label={`选择参数 ${parameter.name}`} aria-describedby={!enabled ? `oi-parameter-restriction-${index}` : undefined} value={parameter.name} checked={parameter.name === selectedName} disabled={!enabled} onChange={() => onSelect(parameter.name)} />
        <span><code>{parameter.kind === 'var_positional' ? '*' : parameter.kind === 'var_keyword' ? '**' : ''}{parameter.name}{parameter.has_default === true ? `=${parameter.default_source ?? '…'}` : ''}</code>
          <small>{KIND_LABELS[parameter.kind] || parameter.kind || '参数类型未提供'} · {enabled ? '可选择' : '不支持'}</small>
          {!enabled && <small className="oi-parameter-restriction" id={`oi-parameter-restriction-${index}`}>{reason}</small>}
        </span>
      </label>)}
    {choices.length > 0 && !choices.some((choice) => choice.enabled) && <p className="oi-parameter-empty">此函数没有可用于当前变更的参数。可切换类型，或返回选择其他函数。</p>}
  </fieldset>;
}

function draftSummary(change, definition) {
  const { changeType, operation } = change;
  const original = definition.parameters?.find((parameter) => parameter.name === operation.parameterName);
  const name = operation.parameterName || '待选择参数';
  if (changeType === 'remove_parameter') return `− ${name}`;
  if (changeType === 'rename_parameter') return `${name} → ${operation.newParameterName || '待填写新名称'}`;
  if (changeType === 'make_parameter_required') return `${name}${original?.has_default === true ? `=${original.default_source ?? '…'}` : ''} → ${name} · 可选 → 必填`;
  return `+ ${operation.parameterName || '待填写参数'} · 必填`;
}

export function ChangeView(props) {
  return props.state.changeDomain === 'symbol' ? <SymbolChangeView {...props} /> : props.state.changeDomain === 'module' ? <ModuleChangeView {...props} /> : <FunctionChangeView {...props} />;
}

function FunctionChangeView({ state, onSelectChangeType, onUpdateChange, onValidate, onAnalyze, navigate }) {
  const selected = getSelectedSymbol(state);
  const validation = state.validation;
  const valid = validation?.validation?.valid === true;
  const busy = Object.values(state.loading).some(Boolean);
  const { changeType, operation } = state.change;
  const type = CHANGE_TYPES.find((item) => item.value === changeType);
  const choices = getParameterChoices(selected, changeType);
  const selectedChoice = choices.find((choice) => choice.parameter.name === operation.parameterName);
  const isAdd = changeType === 'add_required_parameter';
  const isRename = changeType === 'rename_parameter';
  const hasConflict = isAdd && selected?.parameters?.some((parameter) => parameter.name === operation.parameterName.trim());
  const configured = isAdd ? Boolean(operation.parameterName.trim()) && !hasConflict
    : Boolean(selectedChoice?.enabled) && (!isRename || Boolean(operation.newParameterName.trim()));
  const draft = selected ? previewSignature(selected, state.change) : null;
  const validatedDescription = valid ? describeChange(validation.change_spec) : null;
  const draftHighlight = (isRename ? operation.newParameterName : operation.parameterName).trim();
  const removedName = changeType === 'remove_parameter' ? operation.parameterName : undefined;
  const validationDiagnostics = diagnosticCount(validation?.validation?.diagnostics);
  const projectDiagnostics = diagnosticCount(validation?.diagnostics);
  return <div className="oi-workflow-page oi-change-page">
    <section className="page-heading"><div><h1>配置签名变更</h1><p>选择一次参数变化，对照前后签名，再校验并分析调用影响。</p></div><div className="heading-actions"><button className="ghost-action" type="button" onClick={() => navigate('functions')}>返回选择</button></div></section>
    <WorkflowNotes current={3} mode={state.mode} /><ErrorNotice error={state.error} />
    {!selected ? <EmptyWorkflow title="尚未选择目标函数" message="请先读取项目并选择一个模块级函数。" navigate={navigate} /> : <>
      <CoverageNotice coverage={state.inspect?.coverage} />
      <ChangeTypeSelector changeType={changeType} mode={state.mode} onSelect={onSelectChangeType} />
      <section className="oi-change-workspace">
        <article className="oi-change-original" aria-label="目标函数与原始签名"><h2>目标函数</h2><b>{selected.symbol_id}</b><p><code>{selected.file}:{selected.line}</code></p><span className="oi-field-caption">原始签名</span><SignatureText definition={selected} /><p>此处只读取源码。计划变更不会修改上传项目。</p></article>
        <article className="oi-change-input" aria-label={type?.label || '变更配置'}><header><h2>{type?.label || '变更配置'}</h2><span className="oi-change-mark">{isAdd ? '+ 参数' : changeType === 'remove_parameter' ? '− 参数' : isRename ? '名称 →' : '可选 → 必填'}</span></header>
          <form className="oi-change-form" aria-busy={state.loading.validate} onSubmit={(event) => { event.preventDefault(); if (configured && !busy) onValidate(); }}>
            {isAdd ? <>
              <label><span>新增参数名</span><input type="text" value={operation.parameterName} onChange={(event) => onUpdateChange({ parameterName: event.target.value })} placeholder="填写 Python 参数名" required autoComplete="off" aria-invalid={hasConflict || undefined} aria-describedby={hasConflict ? 'oi-parameter-conflict' : undefined} />{hasConflict && <small id="oi-parameter-conflict" className="oi-parameter-restriction" role="status">当前函数已有同名参数，请使用新的名称。</small>}</label>
              <label><span>参数类型</span><select aria-label="参数类型" value={operation.kind} onChange={(event) => onUpdateChange({ kind: event.target.value })}><option value="positional_or_keyword">普通位置或关键字参数</option><option value="positional_only">仅位置参数</option><option value="keyword_only">仅关键字参数</option></select><small><code>{operation.kind}</code></small></label>
              <label><span>插入位置（可选）</span><select aria-label="插入位置（可选）" aria-describedby="oi-insertion-help" value={operation.insertBefore} onChange={(event) => onUpdateChange({ insertBefore: event.target.value })}><option value="">使用后端默认位置</option>{selected.parameters?.map((parameter) => <option value={parameter.name} key={parameter.name}>放在 {parameter.name} 前</option>)}</select><small id="oi-insertion-help">对应 insert_before。参数位置与合法性由后端判断。</small></label>
            </> : <>
              <ParameterSelector choices={choices} selectedName={operation.parameterName} onSelect={(parameterName) => onUpdateChange({ parameterName })} />
              {isRename && <label><span>新参数名</span><input type="text" value={operation.newParameterName} onChange={(event) => onUpdateChange({ newParameterName: event.target.value })} placeholder="填写新的 Python 参数名" required autoComplete="off" /><small>参数的顺序、类型及默认值保持原样；名称合法性由后端校验。</small></label>}
            </>}
            {state.mode === 'demo' && <p className="oi-demo-warning">演示仅接受固定新增参数配置。其他变更类型请上传实际项目。</p>}
            <button className="primary-action" type="submit" disabled={!configured || busy}>{state.loading.validate ? '正在校验…' : '校验变更'}</button>
          </form>
        </article>
        <article className="oi-change-result" aria-label="计划签名与校验结果" aria-busy={state.loading.validate || state.loading.analyze}>
          <header><h2>计划签名</h2><span className={`oi-validation-status${valid ? ' is-valid' : validation ? ' is-invalid' : ''}`} role="status">{state.loading.validate ? '校验中' : validation ? valid ? '已确认变更 · 后端校验通过' : '校验未通过' : '参数草稿 · 尚未校验'}</span></header>
          <div className="oi-signature-before"><span className="oi-field-caption">修改前</span><SignatureText definition={valid ? validation.change_spec.before : selected} removedParameterName={valid ? validatedDescription.removedName : removedName} /></div>
          <div className="oi-signature-after"><span className="oi-field-caption">{valid ? '修改后 · 后端已校验' : validation?.change_spec?.after ? '后端候选签名 · 未通过' : '草稿修改后 · 待校验'}</span>
            {valid ? <SignatureText definition={validation.change_spec.after} highlightParameterName={validatedDescription.highlightName} />
              : validation?.change_spec?.after ? <SignatureText definition={validation.change_spec.after} />
                : draft ? <SignatureText definition={draft} highlightParameterName={removedName ? undefined : draftHighlight} /> : <p className="oi-preview-unavailable">草稿预览不可用，请填写或选择当前变更所需参数。</p>}
            <div className="oi-parameter-draft"><span>{valid ? validatedDescription.detail : draftSummary(state.change, selected)}</span>{!valid && <small>候选签名尚未通过校验，不能据此开始分析。</small>}</div>
          </div>
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
  return <ChangeView state={state} onSelectChangeType={actions.selectChangeType} onUpdateChange={actions.updateChange} onValidate={() => { void actions.validateChange(); }} onAnalyze={analyze} navigate={navigate} />;
}
