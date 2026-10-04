import { useState } from 'react';
import { useWorkflow } from '../state/WorkflowContext.jsx';
import { CoverageNotice, DiagnosticsList, EmptyWorkflow, ErrorNotice, ModeNotice, WorkflowSteps } from './PageParts.jsx';
import { correspondingEvidence, correspondingExplanation, isUsableExplanation, reportFindings, reportIntegrityDiagnostics } from './reportData.js';

function entries(value) {
  return Array.isArray(value) ? value : [];
}

function locationText(location) {
  if (!location?.file) return '位置未提供';
  const line = location.line != null ? `:${location.line}` : '';
  const column = location.column != null ? `:${location.column}` : '';
  return `${location.file}${line}${column}`;
}

function findingLocation(finding) {
  if (finding?.impact_type === 'direct') return finding;
  // Core chooses the shortest existing source path as the representative.
  // Use that same location for the list and an unavailable Evidence fallback.
  const representative = entries(finding?.sources).reduce((shortest, source) =>
    !shortest || entries(source.propagation_path).length < entries(shortest.propagation_path).length ? source : shortest, null);
  return representative?.propagation_path?.[0];
}

function pathText(edges) {
  const path = entries(edges);
  if (!path.length) return '调用路径未提供';
  return [path[0].caller_symbol_id, ...path.map((edge) => edge.callee_symbol_id)].join(' → ');
}

function impactLabel(type) {
  return type === 'direct' ? 'Direct Impact' : type === 'indirect_1hop' ? '1-hop Indirect' : type === 'indirect_2hop' ? '2-hop Indirect' : type || '类型未提供';
}

function AssessmentList({ title, items, manual = false }) {
  if (!entries(items).length) return null;
  return (
    <section className="impact-item" aria-label={title}>
      <header><mark>{manual ? 'Manual Review' : 'Pre-existing Problem'}</mark><b>{title}</b></header>
      <p>{manual
        ? '静态证据不足，需要人工检查；这些记录不计入确定 Direct Impact，也不作为确定间接传播起点。'
        : '修改前已经存在的问题，不归因于本次 Change，也不计入 Direct Impact。'}</p>
      {items.map((item, index) => (
        <section key={index} className="diagnostic-item">
          <b>{item.caller_symbol_id || '调用方未提供'} → {item.target_symbol_id || '目标未提供'}</b>
          <span>位置：{locationText(item)}</span>
          <span>修改前：{item.before_status || '未提供'} · {item.before_reason || '原因未提供'}</span>
          <span>修改后：{item.after_status || '未提供'} · {item.after_reason || '原因未提供'}</span>
          {item.reason && <span>判断依据：{item.reason}</span>}
          {item.rule_id && <span>规则：{item.rule_id}</span>}
          {manual && <span>当前 API 不为人工检查记录生成独立 Evidence 或 Explanation。</span>}
        </section>
      ))}
    </section>
  );
}

function UnresolvedCalls({ calls }) {
  const unresolved = entries(calls);
  return (
    <section className="impact-item" aria-label="未解析调用详情">
      <header><mark>Unresolved</mark><b>未能静态解析的调用</b></header>
      <p>未解析调用不作为确定影响或传播路径。这里只展示接口提供的语法事实及未解析原因。</p>
      {!unresolved.length ? <p>当前报告没有未解析调用记录。</p> : unresolved.map((call, index) => (
        <section className="diagnostic-item" key={index}>
          <b>{locationText(call)}</b>
          <span>调用表达式：<code>{call.expression || '未提供'}</code></span>
          <span>原因：{call.reason || '未提供'}</span>
        </section>
      ))}
    </section>
  );
}

function EvidenceDetails({ finding, evidence, explanationRecord, mode }) {
  const explanation = explanationRecord?.explanation;
  const location = evidence?.location || findingLocation(finding);
  const available = evidence?.status === 'available' && typeof evidence.source_snippet === 'string';
  return (
    <>
      <article className="detail-card evidence-card" aria-label="当前影响的源码证据">
        <header><div className="detail-title"><b>▤</b> {locationText(location)}</div><mark className={`tag ${finding?.impact_type === 'direct' ? 'high' : 'medium'}`}>{finding ? impactLabel(finding.impact_type) : '没有选中项'}</mark></header>
        <section className="info-list">
          <div><span>源码位置</span><b>{locationText(location)}{location?.end_line != null && <small>结束行：{location.end_line}</small>}<small>行号从 1 开始，列偏移从 0 开始。</small></b></div>
        </section>
        {available
          ? <pre className="code-block"><code>{evidence.source_snippet}</code></pre>
          : <section className="state-message">Evidence unavailable：{finding ? '当前记录的源码证据不可用或对应关系不完整。影响记录与计数仍保留。' : '当前没有确定影响记录。'}</section>}
        {!!entries(evidence?.diagnostics).length && <section className="diagnostics-list"><DiagnosticsList diagnostics={evidence.diagnostics} /></section>}
        <section className="explanation-panel" aria-label="当前证据的中文辅助解释"><h3>中文辅助解释</h3>
          {available && isUsableExplanation(explanation)
            ? <><p><b>{explanation.summary}</b></p><p>{explanation.why_affected}</p><p>建议检查：{explanation.suggested_check}</p><p>业务风险：{explanation.risk_level} · 解释置信度：{explanation.confidence}</p></>
            : <p>Explanation unavailable：当前没有可对应的解释，请阅读静态判断原因及诊断。</p>}
          <p>{mode === 'demo' ? '当前演示样例采用规则解释。' : '当前报告未提供 Provider 来源标识，解释可能来自规则或配置的模型。'} 请求成功和解释非空均不能证明 DeepSeek 真实调用成功。</p>
          {!!entries(explanationRecord?.diagnostics).length && <DiagnosticsList diagnostics={explanationRecord.diagnostics} />}
        </section>
      </article>
      <article className="detail-card evidence-meta-card" aria-label="当前影响的证据依据">
        <header><div className="detail-title"><b>⌘</b> 证据依据</div></header>
        <section className="info-list">
          <div><span>规则</span><b>{evidence?.rule || finding?.rule_id || '未提供'}</b></div>
          <div><span>判断原因</span><b>{evidence?.reason || finding?.reason || '未提供'}</b></div>
          <div><span>变更目标</span><b>{evidence?.target_symbol || finding?.target_symbol_id || '未提供'}</b></div>
          <div><span>影响函数</span><b>{finding?.caller_symbol_id || finding?.impacted_symbol_id || '未选择'}</b></div>
          <div><span>调用表达式</span><b><code>{evidence?.call_expression || '未提供'}</code></b></div>
          <div><span>证据状态</span><b>{evidence?.status || 'unavailable'}</b></div>
          <div><span>证据引用</span><b>{evidence?.evidence_reference || '未提供'}</b></div>
          <div><span>源码 SHA256</span><b>{evidence?.source_hash || '未提供'}</b></div>
          {entries(evidence?.propagation_path).map((path, index) => (
            <div key={index}><span>传播路径</span><b>{entries(path.symbols).join(' → ') || '未提供'}
              {entries(path.call_sites).map((site, siteIndex) => <small key={siteIndex}>调用点 {siteIndex + 1}：{locationText(site)}</small>)}
              <small>原始 Direct 引用：{path.direct_evidence_reference || '未提供'}</small>
            </b></div>
          ))}
        </section>
      </article>
    </>
  );
}

// Selection belongs to one Analyze response. A replacement report starts at its
// first finding immediately, without showing the previous report's selection.
export function ReportResults({ report, mode = 'project', initialSelectedIndex = 0 }) {
  const [selection, setSelection] = useState({ report, index: initialSelectedIndex });
  const findings = reportFindings(report);
  const activeIndex = Math.min(selection.report === report ? selection.index : 0, Math.max(0, findings.length - 1));
  const selected = findings[activeIndex];
  const evidence = selected ? correspondingEvidence(report, activeIndex, selected) : null;
  const explanationRecord = selected ? correspondingExplanation(report, activeIndex, evidence) : null;
  const integrityDiagnostics = reportIntegrityDiagnostics(report);
  const metrics = [
    ['直接影响', 'direct_impact_count', '本次变更造成兼容 → 不兼容', 'red', '!'],
    ['1-hop 间接', 'indirect_1hop_count', '上游函数，建议检查', 'amber', '1'],
    ['2-hop 间接', 'indirect_2hop_count', '更上游函数，建议检查', 'amber', '2'],
    ['人工检查', 'manual_review_count', '当前静态证据不足', 'neutral', '□'],
    ['未解析调用', 'unresolved_call_count', '不作为确定影响', 'neutral', '○'],
  ];
  return (
    <>
      <CoverageNotice coverage={report.coverage} />
      {!!integrityDiagnostics.length && <section className="state-message error" role="alert"><b>报告对应关系需要检查。</b><DiagnosticsList diagnostics={integrityDiagnostics} /></section>}
      <section className="change-summary-card">
        <div><span>变更目标</span><b>{report.change?.target_symbol_id || '未提供'}</b></div>
        <div><span>新增参数</span><b>{report.change?.added_parameter?.name || '未提供'}<small>{report.change?.added_parameter?.kind || '参数类型未提供'} · {report.change?.added_parameter?.required === true ? '必填' : '必填状态未提供'}</small></b></div>
        <div><span>变更类型</span><b>{report.change?.change_type === 'add_required_parameter' ? '新增必填参数' : report.change?.change_type || '未提供'}</b></div>
      </section>
      <section className="metric-grid report-metrics" aria-label="影响统计">
        {metrics.map(([title, key, description, color, icon]) => <article className={`metric-card compact-metric${color === 'red' ? ' danger-metric' : color === 'amber' ? ' warn-metric' : ''}`} key={key}><div><span>{title}</span><strong>{report.summary?.[key] ?? '—'}</strong><p>{description}</p></div><div className={`metric-icon ${color}`}>{icon}</div></article>)}
      </section>
      <section className="report-grid">
        <article className="table-card impact-list-card">
          <div className="tabs"><button className="active" type="button">影响列表</button><span>选择记录查看对应证据</span></div>
          <div className="impact-list">
            {findings.map((finding, index) => {
              const direct = finding.impact_type === 'direct';
              return (
                <button className={`impact-item ${direct ? 'direct' : 'indirect'}${finding.impact_type === 'indirect_2hop' ? ' two-hop' : ''}${index === activeIndex ? ' selected' : ''}`} type="button" key={`${finding.impact_type}-${index}`} aria-pressed={index === activeIndex} onClick={() => setSelection({ report, index })}>
                  <header><mark>{impactLabel(finding.impact_type)}</mark><b>{direct ? `${finding.caller_symbol_id} → ${finding.target_symbol_id}` : finding.impacted_symbol_id}</b></header>
                  <p>位置：{locationText(findingLocation(finding))}</p>
                  {direct ? <><p>兼容性：{finding.before_status} → {finding.after_status}</p><p>修改前：{finding.before_reason || '未提供'}</p><p>修改后：{finding.after_reason || '未提供'}</p></> : entries(finding.sources).map((source, sourceIndex) => <section key={sourceIndex}><p>路径：{pathText(source.propagation_path)}</p><p>原始 Direct 调用：{locationText(source.direct_call)} · {source.direct_call?.caller_symbol_id || '未提供'} → {source.direct_call?.target_symbol_id || '未提供'}</p></section>)}
                  <p>原因：{finding.reason || '未提供'}</p>
                </button>
              );
            })}
            {!findings.length && <section className="state-message">当前已解析范围内没有确定 Direct 或 Indirect Impact。{report.coverage?.status === 'partial' ? '覆盖不完整，不能据此判断全项目无影响。' : '请结合人工检查与已有问题阅读结果。'}</section>}
            <AssessmentList title="需要人工检查" items={report.manual_reviews} manual />
            <AssessmentList title="修改前已存在的问题" items={report.pre_existing_problems} />
            <UnresolvedCalls calls={report.diagnostics?.unresolved_calls} />
          </div>
        </article>
        <aside className="detail-column report-detail-column">
          <EvidenceDetails finding={selected} evidence={evidence} explanationRecord={explanationRecord} mode={mode} />
          <article className="detail-card diagnostics-card">
            <header><div className="detail-title"><b>!</b> 诊断 / 分析限制</div><mark className={`tag ${report.coverage?.status === 'complete' ? 'low' : 'medium'}`}>{report.coverage?.status || '未知'}</mark></header>
            <section className="diagnostics-list"><p>Direct 是本次变更造成的兼容性退化。Indirect 表示上游调用路径建议检查，静态路径不保证运行时失败。</p><p>覆盖模块：{report.coverage?.indexed_modules ?? '未提供'} · 覆盖函数：{report.coverage?.indexed_functions ?? '未提供'} · 解析失败文件：{report.coverage?.files_with_parse_errors ?? '未提供'}</p><DiagnosticsList diagnostics={report.diagnostics} /></section>
          </article>
        </aside>
      </section>
    </>
  );
}

export default function ReportPage({ navigate }) {
  const { state } = useWorkflow();
  const report = state.report;
  return (
    <>
      <section className="page-heading"><div><h1>分析报告</h1><p>{report ? '查看调用兼容性变化、上游调用路径、源码证据和对应解释。' : '当前会话尚未产生分析报告。'}</p></div><div className="heading-actions"><span>覆盖状态 <b>{report?.coverage?.status || '尚未分析'}</b></span><button className="ghost-action" type="button" onClick={() => navigate('change')}>调整变更</button></div></section>
      <WorkflowSteps current={4} /><ModeNotice mode={state.mode} /><ErrorNotice error={state.error} />
      {!report ? <EmptyWorkflow title="没有当前项目的报告" message="请先选择函数并校验变更。刷新浏览器后需重新选择 ZIP，演示样例只在明确开启演示模式后展示。" navigate={navigate} /> : <ReportResults report={report} mode={state.mode} />}
    </>
  );
}
