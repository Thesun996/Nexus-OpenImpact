import ModuleReportView from './ModuleReportView.jsx';
import SymbolReportView from './SymbolReportView.jsx';
import { useRef, useState } from 'react';
import { useWorkflow } from '../state/WorkflowContext.jsx';
import { formatSignature } from '../state/workflow.js';
import { describeChange } from '../state/changeDraft.js';
import { CoverageNotice, DiagnosticsList, EmptyWorkflow, ErrorNotice, ModeNotice, WorkflowSteps } from './PageParts.jsx';
import { correspondingEvidence, correspondingExplanation, reportFindings, reportIntegrityDiagnostics } from './reportData.js';
import ImpactIndex from '../components/report/ImpactIndex.jsx';
import TraceView from '../components/report/TraceView.jsx';
import EvidencePanel from '../components/report/EvidencePanel.jsx';
import ExplanationPanel from '../components/report/ExplanationPanel.jsx';
import ReviewNotes, { ReportDiagnostics } from '../components/report/ReviewNotes.jsx';
import ImpactCounts from '../components/report/ImpactCounts.jsx';
import { entries, impactLabel, statusLabel } from '../components/report/presentation.js';
import '../components/report/report.css';

export function ChangeOverview({ change }) {
  const description = describeChange(change);
  return <section className="oi-change-overview" aria-label="当前计划变更">
    <div className="oi-change-target"><span>计划变更</span><b>{change?.target_symbol_id || '未提供'}</b></div>
    <div className="oi-change-parameter"><span>{description.label}</span><code>{description.detail}</code></div>
    <div className="oi-planned-signatures">
      <div><span>修改前</span><code>{change?.before ? formatSignature(change.before) : '未提供'}</code></div>
      <div><span>修改后</span><code>{change?.after ? formatSignature(change.after) : '未提供'}</code></div>
    </div>
    <p>此处展示后端已校验的计划签名，用户源码保持原样。变更类型：{description.label}。</p>
  </section>;
}

// Keep selection scoped to one Analyze response. A replacement report immediately
// starts at its first finding, without inheriting the previous report's index.
export function ReportResults(props) {
  if (props.report.change_domain === 'symbol') {
    return props.report.report_kind === 'symbol_impact' && props.report.schema_version === 1
      ? <SymbolReportView report={props.report} /> : <section className="state-message error" role="alert">符号报告版本不可识别，请检查后端契约。</section>;
  }
  if (props.report.change_domain === 'module') {
    return props.report.report_kind === 'module_impact' && props.report.schema_version === 1
      ? <ModuleReportView report={props.report} /> : <section className="state-message error" role="alert">模块报告版本不可识别，请检查后端契约。</section>;
  }
  return <FunctionReportResults {...props} />;
}

function FunctionReportResults({ report, mode = 'project', initialSelectedIndex = 0 }) {
  const [selection, setSelection] = useState({ report, index: initialSelectedIndex });
  const manualRef = useRef(null);
  const unresolvedRef = useRef(null);
  const preexistingRef = useRef(null);
  const sectionRefs = { manual: manualRef, unresolved: unresolvedRef, preexisting: preexistingRef };
  const findings = reportFindings(report);
  const activeIndex = Math.min(selection.report === report ? selection.index : 0, Math.max(0, findings.length - 1));
  const selected = findings[activeIndex];
  const evidence = selected ? correspondingEvidence(report, activeIndex, selected) : null;
  const explanationRecord = selected ? correspondingExplanation(report, activeIndex, evidence) : null;
  const integrityDiagnostics = reportIntegrityDiagnostics(report);
  const reviewCounts = {
    manual: entries(report.manual_reviews).length,
    unresolved: entries(report.diagnostics?.unresolved_calls).length,
    preexisting: entries(report.pre_existing_problems).length,
  };

  function showReview(key) {
    // In-page presentation navigation must not change the application's hash route.
    const section = sectionRefs[key]?.current;
    section?.scrollIntoView({ block: 'start', behavior: 'auto' });
    section?.focus({ preventScroll: true });
  }

  return <section className="oi-report">
    <CoverageNotice coverage={report.coverage} />
    {!!integrityDiagnostics.length && <section className="state-message error" role="alert"><b>报告对应关系需要检查。</b><DiagnosticsList diagnostics={integrityDiagnostics} /></section>}
    <ChangeOverview change={report.change} />
    <ImpactCounts summary={report.summary} />
    <div className="oi-report-workspace">
      <ImpactIndex findings={findings} activeIndex={activeIndex}
        onSelect={(index) => setSelection({ report, index })} reviewCounts={reviewCounts} onReview={showReview} />
      <div className="oi-report-reading">
        {selected ? <div key={activeIndex} className="oi-selected-evidence" data-evidence-slot={activeIndex}>
          <p className="oi-selected-record" aria-live="polite">当前记录：<b>{selected.caller_symbol_id || selected.impacted_symbol_id || '未提供'}</b><span>{impactLabel(selected.impact_type)}</span></p>
          <TraceView finding={selected} evidence={evidence} />
          <div className="oi-reading-panes">
            <EvidencePanel finding={selected} evidence={evidence} />
            <ExplanationPanel evidence={evidence} explanationRecord={explanationRecord} mode={mode} />
          </div>
        </div> : <div className="oi-report-empty" role="status">
          <span aria-hidden="true">∅</span><h2>当前没有确定影响</h2>
          <p>当前已解析范围内没有确定直接影响或间接影响。{report.coverage?.status === 'partial' ? '覆盖不完整，不能据此判断全项目无影响。' : '请结合人工检查与已有问题阅读结果。'}</p>
          <p>没有对应的传播路径、源码证据和中文解释，页面保留真实零结果。</p>
        </div>}
        <ReviewNotes report={report} sectionRefs={sectionRefs} />
        <ReportDiagnostics report={report} />
      </div>
    </div>
  </section>;
}

export default function ReportPage({ navigate }) {
  const { state } = useWorkflow();
  const report = state.report;
  return <div className="oi-report-page">
    <section className="page-heading"><div><h1>分析报告</h1><p>{report ? report.change_domain === 'symbol' ? '从静态符号引用追到真实定义与源码证据。' : report.change_domain === 'module' ? '从静态导入依赖追到真实源码，理解拟定模块变更。' : '从调用路径追到真实源码，理解这次变更的影响。' : '当前会话尚未产生分析报告。'}</p></div><div className="heading-actions"><span>覆盖状态 <b>{report ? statusLabel(report.coverage?.status) : '尚未分析'}</b></span><button className="ghost-action" type="button" onClick={() => navigate('change')}>调整变更</button></div></section>
    <details className="oi-report-process"><summary>分析流程与会话说明</summary><WorkflowSteps current={4} /><ModeNotice mode={state.mode} /></details>
    <ErrorNotice error={state.error} />
    {!report ? <EmptyWorkflow title="没有当前项目的报告" message="请先选择函数并校验变更。刷新浏览器后需重新选择 ZIP，演示样例只在明确开启演示模式后展示。" navigate={navigate} /> : <ReportResults report={report} mode={state.mode} />}
  </div>;
}
