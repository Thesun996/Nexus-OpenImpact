import { statusLabel } from '../../presentation/labels.js';
import { formatSignature } from '../../state/workflow.js';
import { DiagnosticsList, ModeNotice, WorkflowSteps } from '../../pages/PageParts.jsx';
import './workflow-pages.css';

export function WorkflowNotes({ current, mode }) {
  return <details className="oi-workflow-process"><summary>流程与会话说明</summary><WorkflowSteps current={current} /><ModeNotice mode={mode} /></details>;
}

export function ProjectOverview({ inspect, file, fingerprint, mode }) {
  return <section className="oi-project-overview" aria-label="已读取项目概览">
    <div className="oi-project-identity"><span>{mode === 'demo' ? '独立演示项目' : '本次 ZIP 的项目'}</span><h2>{inspect.project_name || '项目名称未提供'}</h2><code>{file?.name || '文件名未提供'}</code></div>
    <dl className="oi-project-facts"><div><dt>模块</dt><dd>{inspect.modules?.length ?? '—'}</dd></div><div><dt>函数</dt><dd>{inspect.symbols?.length ?? '—'}</dd></div><div><dt>覆盖</dt><dd className={inspect.coverage?.status === 'complete' ? 'is-complete' : ''}>{statusLabel(inspect.coverage?.status)}</dd></div></dl>
    <details className="oi-project-details"><summary>模块与项目指纹</summary><p>项目指纹 <code>{fingerprint || '未提供'}</code></p><ul>{(inspect.modules || []).map((module, index) => <li key={`${module.module}-${index}`}><code>{module.module || '模块名未提供'}</code><span>{module.file || '路径未提供'}</span><small>{statusLabel(module.parse_status)}</small></li>)}</ul></details>
  </section>;
}

// Presentation only: reuse the formatter and highlight a parameter's own name,
// leaving unrelated annotation/default text and the source definition intact.
export function SignatureText({ definition, addedParameterName, highlightParameterName, removedParameterName }) {
  const highlightedName = removedParameterName || highlightParameterName || addedParameterName;
  const parameter = definition?.parameters?.find(item => item.name === highlightedName);
  if (!parameter) return <code className="oi-signature-text">{formatSignature(definition)}</code>;
  const marker = '\u0000'; // This delimiter cannot occur in Python source.
  const display = { ...definition, parameters: definition.parameters.map(item => item === parameter ? { ...item, name: marker } : item) };
  const [before, after] = formatSignature(display).split(marker);
  return <code className="oi-signature-text">{before}{removedParameterName
    ? <del className="oi-removed-parameter">{parameter.name}</del>
    : <mark className="oi-added-parameter">{parameter.name}</mark>}{after}</code>;
}

export function diagnosticCount(diagnostics) {
  return Array.isArray(diagnostics) ? diagnostics.length : Object.values(diagnostics || {}).reduce((total, values) => total + (Array.isArray(values) ? values.length : 0), 0);
}

export function ProjectDiagnostics({ diagnostics, coverage }) {
  const count = diagnosticCount(diagnostics);
  return <details className="oi-project-diagnostics" open={count > 0 || coverage?.status === 'partial'}><summary>解析诊断 <span>{count} 条记录</span></summary><DiagnosticsList diagnostics={diagnostics} /></details>;
}
