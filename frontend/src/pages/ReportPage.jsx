import { useState } from 'react';
import { useWorkflow } from '../state/WorkflowContext.jsx';
import { CoverageNotice, DiagnosticsList, EmptyWorkflow, ErrorNotice, ModeNotice, WorkflowSteps } from './PageParts.jsx';
import { correspondingEvidence, correspondingExplanation } from './reportData.js';

function locationText(location) {
  return location?.file ? `${location.file}${location.line != null ? `:${location.line}` : ''}` : '位置未提供';
}

function pathText(edges = []) {
  if (!edges.length) return '调用路径未提供';
  return [edges[0].caller_symbol_id, ...edges.map((edge) => edge.callee_symbol_id)].join(' → ');
}

function impactLabel(type) {
  return type === 'direct' ? 'Direct Impact' : type === 'indirect_1hop' ? '1-hop Indirect' : type === 'indirect_2hop' ? '2-hop Indirect' : type;
}

export default function ReportPage({ navigate }) {
  const { state } = useWorkflow();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const report = state.report;
  const findings = [...(report?.direct_impacts || []), ...(report?.indirect_impacts || [])];
  const activeIndex = Math.min(selectedIndex, Math.max(0, findings.length - 1));
  const selected = findings[activeIndex];
  const evidence = report && selected ? correspondingEvidence(report, activeIndex, selected) : null;
  const explanationRecord = report && selected ? correspondingExplanation(report, activeIndex, evidence) : null;
  const explanation = explanationRecord?.explanation;
  const metrics = [
    ['直接影响', 'direct_impact_count', '本次变更造成兼容 → 不兼容', 'red', '!'],
    ['1-hop 间接', 'indirect_1hop_count', '上游函数，建议检查', 'amber', '1'],
    ['2-hop 间接', 'indirect_2hop_count', '更上游函数，建议检查', 'amber', '2'],
    ['人工检查', 'manual_review_count', '当前静态证据不足', 'neutral', '□'],
    ['未解析调用', 'unresolved_call_count', '不作为确定影响', 'neutral', '○'],
  ];

  return (
    <>
      <section className="page-heading"><div><h1>分析报告</h1><p>{report ? '查看调用兼容性变化、上游调用路径、源码证据和对应解释。' : '当前会话尚未产生分析报告。'}</p></div><div className="heading-actions"><span>覆盖状态 <b>{report?.coverage?.status || '尚未分析'}</b></span><button className="ghost-action" type="button" onClick={() => navigate('change')}>调整变更</button></div></section>
      <WorkflowSteps current={4} symbol={state.selectedSymbolId} /><ModeNotice mode={state.mode} /><ErrorNotice error={state.error} />
      {!report ? <EmptyWorkflow title="没有当前项目的报告" message="请先选择函数并校验变更。演示样例只会在明确开启演示模式后展示。" navigate={navigate} /> : <>
        <CoverageNotice coverage={report.coverage} />
        <section className="change-summary-card"><div><span>变更目标</span><b>{report.change?.target_symbol_id || '未提供'}</b></div><div><span>新增参数</span><b>{report.change?.added_parameter?.name || '未提供'}</b></div><div><span>变更类型</span><b>{report.change?.change_type === 'add_required_parameter' ? '新增必填参数' : report.change?.change_type || '未提供'}</b></div></section>
        <section className="metric-grid report-metrics" aria-label="影响统计">
          {metrics.map(([title, key, description, color, icon]) => <article className={`metric-card compact-metric${color === 'red' ? ' danger-metric' : color === 'amber' ? ' warn-metric' : ''}`} key={key}><div><span>{title}</span><strong>{report.summary?.[key] ?? '—'}</strong><p>{description}</p></div><div className={`metric-icon ${color}`}>{icon}</div></article>)}
        </section>
        <section className="report-grid">
          <article className="table-card impact-list-card">
            <div className="tabs"><button className="active" type="button">影响列表</button><span>选择记录查看对应证据</span></div>
            <div className="impact-list">
              {findings.map((finding, index) => {
                const direct = finding.impact_type === 'direct';
                const firstEdge = finding.sources?.[0]?.propagation_path?.[0];
                return <button className={`impact-item ${direct ? 'direct' : 'indirect'}${finding.impact_type === 'indirect_2hop' ? ' two-hop' : ''}${index === activeIndex ? ' selected' : ''}`} type="button" key={`${finding.impact_type}-${finding.file || finding.impacted_symbol_id}-${finding.line || index}-${index}`} aria-pressed={index === activeIndex} onClick={() => setSelectedIndex(index)}>
                  <header><mark>{impactLabel(finding.impact_type)}</mark><b>{direct ? `${finding.caller_symbol_id} → ${finding.target_symbol_id}` : finding.impacted_symbol_id}</b></header>
                  <p>位置：{locationText(direct ? finding : firstEdge)}</p>
                  {direct ? <p>兼容性：{finding.before_status} → {finding.after_status}</p> : finding.sources?.map((source, sourceIndex) => <p key={sourceIndex}>路径：{pathText(source.propagation_path)}</p>)}
                  <p>原因：{finding.reason}</p>
                </button>;
              })}
              {!findings.length && <section className="state-message">当前已解析范围内没有确定 Direct 或 Indirect Impact。{report.coverage?.status === 'partial' ? '覆盖不完整，不能据此判断全项目无影响。' : '请结合人工检查与已有问题阅读结果。'}</section>}
              {!!report.manual_reviews?.length && <section className="impact-item"><header><mark>Manual Review</mark><b>需要人工检查</b></header>{report.manual_reviews.map((item, index) => <p key={index}>{locationText(item)} · {item.reason || item.after_reason || '静态证据不足，不能确定本次变更的影响。'}</p>)}</section>}
              {!!report.pre_existing_problems?.length && <section className="impact-item"><header><mark>Pre-existing Problem</mark><b>修改前已存在的问题</b></header>{report.pre_existing_problems.map((item, index) => <p key={index}>{locationText(item)} · {item.before_reason || item.reason || '不计入本次 Direct Impact。'}</p>)}</section>}
            </div>
          </article>
          <aside className="detail-column report-detail-column">
            <article className="detail-card evidence-card">
              <header><div className="detail-title"><b>▤</b> {locationText(evidence?.location)}</div><mark className={`tag ${selected?.impact_type === 'direct' ? 'high' : 'medium'}`}>{selected ? impactLabel(selected.impact_type) : '没有选中项'}</mark></header>
              {evidence?.status === 'available' && evidence.source_snippet != null ? <pre className="code-block"><code>{evidence.source_snippet}</code></pre> : <section className="state-message">Evidence unavailable：{selected ? '当前记录的源码证据不可用或对应关系不完整。影响记录与计数仍保留。' : '当前没有影响记录。'}</section>}
              <section className="explanation-panel"><h3>中文辅助解释</h3>
                {explanation ? <><p><b>{explanation.summary}</b></p><p>{explanation.why_affected}</p><p>建议检查：{explanation.suggested_check}</p><p>业务风险：{explanation.risk_level} · 解释置信度：{explanation.confidence}</p></> : <p>Explanation unavailable：当前没有可对应的解释，请阅读静态判断原因及诊断。</p>}
                <p>{state.mode === 'demo' ? '当前演示样例采用规则解释。' : '当前报告未提供 Provider 来源标识。'} API 未提供模型成功或 fallback 状态，不能据响应成功或 confidence 推断 DeepSeek 已成功调用。</p>
                {!!explanationRecord?.diagnostics?.length && <DiagnosticsList diagnostics={explanationRecord.diagnostics} />}
              </section>
            </article>
            <article className="detail-card evidence-meta-card"><header><div className="detail-title"><b>⌘</b> 证据依据</div></header><section className="info-list"><div><span>规则</span><b>{evidence?.rule || selected?.rule_id || '未提供'}</b></div><div><span>变更目标</span><b>{evidence?.target_symbol || report.change?.target_symbol_id || '未提供'}</b></div><div><span>影响函数</span><b>{selected?.caller_symbol_id || selected?.impacted_symbol_id || '未选择'}</b></div><div><span>调用表达式</span><b>{evidence?.call_expression || '未提供'}</b></div><div><span>证据状态</span><b>{evidence?.status || 'unavailable'}</b></div><div><span>证据引用</span><b>{evidence?.evidence_reference || '未提供'}</b></div><div><span>源码 SHA256</span><b>{evidence?.source_hash || '未提供'}</b></div>
              {evidence?.propagation_path?.map((path, index) => <div key={index}><span>传播路径</span><b>{path.symbols?.join(' → ')}<small>Direct 引用：{path.direct_evidence_reference}</small></b></div>)}
            </section>{!!evidence?.diagnostics?.length && <section className="diagnostics-list"><DiagnosticsList diagnostics={evidence.diagnostics} /></section>}</article>
            <article className="detail-card diagnostics-card"><header><div className="detail-title"><b>!</b> 诊断 / 分析限制</div><mark className={`tag ${report.coverage?.status === 'complete' ? 'low' : 'medium'}`}>{report.coverage?.status || '未知'}</mark></header><section className="diagnostics-list"><p>Direct 是本次变更造成的兼容性退化。Indirect 表示上游调用路径建议检查，静态路径不保证运行时失败。</p><DiagnosticsList diagnostics={report.diagnostics} /></section></article>
          </aside>
        </section>
      </>}
    </>
  );
}
