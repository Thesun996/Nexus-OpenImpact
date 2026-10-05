import ExplanationText from '../components/report/ExplanationText.jsx';
import { riskLabel, statusLabel, ruleLabel, reasonLabel } from '../components/report/presentation.js';
import { moduleDiagnosticEntries } from './moduleReportData.js';
import { useState } from 'react';
import { CoverageNotice, DiagnosticsList } from './PageParts.jsx';
import { moduleFindings, moduleEvidence, moduleExplanation, moduleImpactLabel } from './moduleReportData.js';
import { isUsableExplanation } from './reportData.js';

export default function ModuleReportView({ report }) {
  const [selection, setSelection] = useState({ report, index: 0 });
  const findings = moduleFindings(report);
  const index = Math.min(selection.report === report ? selection.index : 0, Math.max(0, findings.length - 1));
  const finding = findings[index];
  const evidence = finding ? moduleEvidence(report, index, finding) : null;
  const record = evidence ? moduleExplanation(report, index, evidence) : null;
  const explanation = record?.explanation;
  const change = report.change;
  const summary = report.summary;
  const counts = [['确定影响', '直接导入', summary.direct_import_count], ['依赖传播', '1 层上游模块', summary.indirect_1hop_module_count],
    ['依赖传播', '2 层上游模块', summary.indirect_2hop_module_count], ['分析边界', '人工检查', summary.manual_review_count], ['分析边界', '未解析导入', summary.unresolved_import_count]];
  return <section className="oi-report oi-module-report" data-report-domain="module">
    <CoverageNotice coverage={report.coverage} />
    <section className="oi-change-overview" aria-label="当前计划模块变更">
      <div className="oi-change-target"><span>目标模块</span><b>{change.target_module_id}</b></div>
      <div className="oi-change-parameter"><span>{change.change_type === 'rename_module' ? '重命名模块' : '删除模块'}</span><code>{change.before.file} → {change.after?.file || '拟定移除'}</code></div>
      <p>只分析虚拟项目布局，不重命名或删除源码。直接影响统计真实导入引用；间接影响按上游模块去重，不代表确定运行失败。</p>
    </section>
    <div className="oi-module-counts" aria-label="模块影响统计">{counts.map(([group, label, value]) => <div key={label}><small>{group}</small><b>{value ?? 0}</b><span>{label}</span></div>)}</div>
    <p className="oi-explanation-note">{report.coverage.message}</p>
    <div className="oi-report-workspace">
      <section className="oi-impact-index" aria-label="模块影响索引"><header><h2>导入影响索引</h2><span>{findings.length} 条</span></header>
        {findings.map((item, slot) => <button className={`oi-symbol-row${slot === index ? ' is-selected' : ''}`} type="button" aria-pressed={slot === index} key={item.finding_id} onClick={() => setSelection({ report, index: slot })}>
          <span>{moduleImpactLabel(item.impact_type)}</span><b>{item.impacted_module_id}</b><span>{item.location?.file || item.propagation_path?.[0]?.import_sites?.[0]?.file}</span>
        </button>)}{!findings.length && <p>当前没有确定的导入或上游传播影响。</p>}
      </section>
      <div className="oi-report-reading">{finding ? <div key={finding.finding_id} className="oi-selected-evidence">
        <p className="oi-selected-record" aria-live="polite">当前记录：<b>{finding.impacted_module_id}</b><span>{moduleImpactLabel(finding.impact_type)}</span></p>
        <section className="oi-trace-view"><h2>静态模块依赖路径</h2>
          {evidence?.propagation_path?.length ? evidence.propagation_path.map((path, pathIndex) => <div className="oi-module-path" key={`${path.source_direct_impact}-${pathIndex}`}><ol>{path.modules.map((module, step) => <li key={`${module}-${step}`}><code>{module}</code>{step < path.modules.length - 1 && <span aria-hidden="true"> → </span>}</li>)}</ol><details><summary>直接影响来源（定位编号）</summary><code>{path.source_direct_impact}</code></details></div>) : <p>路径暂不可用：没有可对应的真实传播证据。</p>}
          <p>代表性静态依赖路径，未展示完整项目图；上游模块仅建议检查。</p>
        </section>
        <div className="oi-reading-panes"><article className="oi-evidence-panel" aria-label="当前导入的源码证据"><header><div><h2>导入源码证据</h2><code>{evidence?.location?.file || finding.location?.file || '未提供'}:{evidence?.location?.line || finding.location?.line || '?'}</code></div><span>{statusLabel(evidence?.status || 'unavailable')}</span></header>
          {evidence?.status === 'available' && typeof evidence.source_snippet === 'string' ? <div className="oi-code-reading"><span className="oi-source-line">{evidence.location.line}</span><pre className="code-block" tabIndex={0} aria-label="导入源码片段"><code>{evidence.source_snippet}</code></pre></div> : <div className="oi-report-unavailable" role="status"><b>源码证据暂不可用</b><p>当前记录证据缺失或元数据不匹配，不借用其他项源码。</p></div>}
          <dl className="oi-static-facts"><div><dt>静态规则</dt><dd>{ruleLabel(evidence?.rule || finding.rule)}</dd></div><div><dt>判断依据</dt><dd>{reasonLabel(finding.reason)}</dd></div><div><dt>证据引用</dt><dd><details><summary>查看定位编号</summary><code>{evidence?.evidence_reference || finding.finding_id}</code></details></dd></div></dl>
          {finding.impact_type === 'direct_import' && <div className="oi-compatibility-proof"><h3>项目导入绑定变化</h3><p>变更前：{statusLabel(finding.before_resolution.status)} → {finding.before_resolution.target_module_id}</p><p>变更后：{statusLabel(finding.after_resolution.status)} · {reasonLabel(finding.after_resolution.reason)}</p></div>}
          <details className="oi-evidence-metadata"><summary>证据元数据</summary><p>原始绑定信息：<code>{JSON.stringify({ before: finding.before_resolution?.status, after: finding.after_resolution?.status, reason: finding.after_resolution?.reason })}</code></p><p>原始规则编号：<code>{evidence?.rule || finding.rule || '未提供'}</code></p><p><code>{evidence?.import_expression || '未提供'}</code></p><p>源码 SHA256：<code>{evidence?.source_hash || '未提供'}</code></p><DiagnosticsList diagnostics={evidence?.diagnostics} showEmptyState={false} /></details>
        </article><aside className="oi-explanation-panel" aria-label="当前导入的中文辅助解释"><h2>中文辅助解释</h2>
          {isUsableExplanation(explanation) ? <><p className="oi-explanation-summary">{explanation.summary}</p><ExplanationText text={explanation.why_affected} /><h3>建议检查</h3><ExplanationText text={explanation.suggested_check} ordered /><p className="oi-explanation-note">规则解释 · 业务风险 {riskLabel(explanation.risk_level)} · 解释置信度 {explanation.confidence}，不表示运行失败概率。</p></> : <div className="oi-report-unavailable"><b>解释暂不可用</b><p>请直接阅读静态证据与诊断。</p></div>}
        </aside></div>
      </div> : <div className="oi-report-empty" role="status"><span>∅</span><h2>当前没有确定影响</h2><p>{report.coverage.status === 'partial' ? '覆盖不完整，零结果不证明项目没有其他影响。' : '受支持的静态引用未因本次虚拟模块变更产生断裂。'}</p><p>没有对应的源码证据与解释，不使用演示 数据填充。</p></div>}
        <section className="oi-review-section"><h2>分析边界与诊断</h2><p>条件、局部、动态、相对和复杂包导入保持人工检查或未解析，不参与确定传播。</p><DiagnosticsList diagnostics={moduleDiagnosticEntries(report.diagnostics)} /></section>
      </div>
    </div>
  </section>;
}
