import { DiagnosticsList } from '../../pages/PageParts.jsx';
import { entries, findingLocation, locationText, statusLabel, ruleLabel, reasonLabel } from './presentation.js';

import { SourceLink } from '../workspace/SourceWorkspace.jsx';

export default function EvidencePanel({ finding, evidence }) {
  const location = evidence?.location || findingLocation(finding);
  const available = evidence?.status === 'available' && typeof evidence.source_snippet === 'string';
  return (
    <article className="oi-evidence-panel" aria-label="当前影响的源码证据">
      <header><div><h2>源码证据</h2><code>{locationText(location)}</code></div><span className="oi-evidence-status">{available ? '可用' : '不可用'}</span></header>
      <SourceLink location={location} sourceHash={evidence?.source_hash} />
      {available
        ? <div className="oi-code-reading"><span className="oi-source-line" aria-hidden="true">{location?.line ?? '—'}</span><pre className="code-block" tabIndex={0} aria-label="源码片段，可横向滚动"><code>{evidence.source_snippet}</code></pre></div>
        : <div className="oi-report-unavailable" role="status"><b>源码证据暂不可用</b><p>当前记录的源码证据不可用或对应关系不完整。影响记录与计数仍保留。</p></div>}
      {!!entries(evidence?.diagnostics).length && <div className="oi-evidence-diagnostics"><DiagnosticsList diagnostics={evidence.diagnostics} /></div>}
      <dl className="oi-static-facts">
        <div><dt>静态规则</dt><dd>{ruleLabel(evidence?.rule || finding?.rule_id)}</dd></div>
        <div className="oi-evidence-reason"><dt>判断依据</dt><dd>{reasonLabel(evidence?.reason || finding?.reason) || '未提供'}</dd></div>
        <div><dt>证据引用</dt><dd><details><summary>查看定位编号</summary><code>{evidence?.evidence_reference || '未提供'}</code></details></dd></div>
      </dl>
      {finding?.impact_type === 'direct' && <div className="oi-compatibility-proof">
        <h3>调用兼容性变化</h3>
        <p><span>修改前 {statusLabel(finding.before_status)}</span>{finding.before_reason || '原因未提供'}</p>
        <p><span>修改后 {statusLabel(finding.after_status)}</span>{finding.after_reason || '原因未提供'}</p>
      </div>}
      <details className="oi-evidence-metadata">
        <summary>证据元数据</summary>
        <dl className="oi-static-facts">
          <div><dt>原始规则编号</dt><dd><code>{evidence?.rule || finding?.rule_id || '未提供'}</code></dd></div>
          <div><dt>变更目标</dt><dd><code>{evidence?.target_symbol || finding?.target_symbol_id || '未提供'}</code></dd></div>
          <div><dt>影响函数</dt><dd><code>{finding?.caller_symbol_id || finding?.impacted_symbol_id || '未提供'}</code></dd></div>
          <div><dt>调用表达式</dt><dd><code>{evidence?.call_expression || '未提供'}</code></dd></div>
          <div><dt>源码位置</dt><dd>{locationText(location)}{location?.end_line != null && <small>结束行：{location.end_line}</small>}<small>行号从 1 开始，列偏移从 0 开始。</small></dd></div>
          <div><dt>源码 SHA256</dt><dd><code>{evidence?.source_hash || '未提供'}</code><small>完整源码文件原始字节的 SHA-256。</small></dd></div>
        </dl>
      </details>
    </article>
  );
}
