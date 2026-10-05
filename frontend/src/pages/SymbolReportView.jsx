import { useState } from 'react';
import { CoverageNotice, DiagnosticsList } from './PageParts.jsx';
import { symbolFindings, symbolEvidence, symbolExplanation, symbolImpactLabel, symbolDiagnosticEntries } from './symbolReportData.js';
import { isUsableExplanation } from './reportData.js';

export default function SymbolReportView({ report }) {
  const [selection, setSelection] = useState({ report, index: 0 });
  const findings = symbolFindings(report), index = Math.min(selection.report === report ? selection.index : 0, Math.max(0, findings.length - 1));
  const finding = findings[index], evidence = finding ? symbolEvidence(report, index, finding) : null;
  const explanation = symbolExplanation(report, index, evidence)?.explanation;
  const { change, summary } = report;
  const counts = [['确定影响', '直接符号引用', summary.direct_reference_count], ['依赖传播', '1 层上游模块', summary.indirect_1hop_module_count], ['依赖传播', '2 层上游模块', summary.indirect_2hop_module_count], ['分析边界', '人工检查', summary.manual_review_count], ['分析边界', '未解析引用', summary.unresolved_reference_count]];
  return <section className="oi-report oi-symbol-report" data-report-domain="symbol">
    <CoverageNotice coverage={report.coverage} />
    <section className="oi-change-overview" aria-label="当前计划符号变更"><div className="oi-change-target"><span>目标符号</span><b>{change.target_symbol_id}</b></div><div className="oi-change-parameter"><span>{change.change_type === 'rename_module_symbol' ? '重命名模块符号' : '删除模块符号'}</span><code>{change.before.name} → {change.after?.name || '拟定移除'}</code></div><div className="oi-planned-signatures"><div><span>原始定义</span><code>{change.before.definition}</code></div><div><span>虚拟定义</span><code>{change.after?.definition || '不再提供该定义'}</code></div></div><p>不修改源码。Direct 按真实引用位置计数；导入与读取为独立位置。上游模块按模块去重，只建议检查。</p></section>
    <div className="oi-module-counts" aria-label="符号影响统计">{counts.map(([group,label,value]) => <div key={label}><small>{group}</small><b>{value ?? 0}</b><span>{label}</span></div>)}</div>
    <div className="oi-report-workspace"><section className="oi-impact-index" aria-label="符号影响索引"><header><h2>符号引用索引</h2><span>{findings.length} 条</span></header>{findings.map((item,slot) => <button className={`oi-symbol-row${slot === index ? ' is-selected' : ''}`} aria-pressed={slot === index} key={item.finding_id} onClick={() => setSelection({ report, index: slot })}><span>{symbolImpactLabel(item.impact_type)}</span><b>{item.impacted_module_id}</b><span>{item.location?.file || item.propagation_path?.[0]?.import_sites?.[0]?.file}</span></button>)}{!findings.length && <p>当前没有确定的符号引用或上游传播影响。</p>}</section>
      <div className="oi-report-reading">{finding ? <div key={finding.finding_id} className="oi-selected-evidence">
        <p className="oi-selected-record" aria-live="polite">当前记录：<b>{finding.impacted_module_id}</b><span>{symbolImpactLabel(finding.impact_type)}</span></p>
        <section className="oi-trace-view"><h2>上游模块依赖与终端引用</h2>{evidence?.status === 'available' ? evidence.propagation_path?.length ? evidence.propagation_path.map((path, slot) => <div className="oi-module-path" key={`${path.source_direct_impact}-${slot}`}><ol>{path.modules.map((module,step) => <li key={`${module}-${step}`}><code>{module}</code>{step < path.modules.length-1 && <span aria-hidden="true"> → </span>}</li>)}</ol><p>终端符号引用：<code>{path.terminal_reference.expression}</code> · {path.terminal_reference.file}:{path.terminal_reference.line}</p></div>) : <p>当前记录为直接符号引用：<code>{evidence.reference_expression}</code>。没有上游传播路径，不推测额外关系。</p> : <p>Trace unavailable：没有可匹配的当前证据。</p>}<p>代表性静态路径，未展示完整项目图；上游只需检查，不代表确定运行失败。</p></section>
        <div className="oi-reading-panes"><article className="oi-evidence-panel" aria-label="符号源码证据"><header><div><h2>源码证据</h2><code>{evidence?.location?.file || finding.location?.file || 'unavailable'}:{evidence?.location?.line || finding.location?.line || '?'}</code></div><span>{evidence?.status || 'unavailable'}</span></header>
          {evidence?.status === 'available' && typeof evidence.source_snippet === 'string' ? <div className="oi-code-reading"><span className="oi-source-line">{evidence.location.line}</span><pre className="code-block" tabIndex={0}><code>{evidence.source_snippet}</code></pre></div> : <div className="oi-report-unavailable" role="status"><b>Evidence unavailable</b><p>证据缺失或元数据不匹配，不借用其他记录源码。</p></div>}
          <dl className="oi-static-facts"><div><dt>静态规则</dt><dd><code>{evidence?.rule || finding.rule || 'upstream_symbol_dependency_review'}</code></dd></div><div><dt>判断依据</dt><dd>{finding.reason}</dd></div><div><dt>证据引用</dt><dd><code>{finding.finding_id}</code></dd></div></dl>
          {finding.before_resolution && <div className="oi-compatibility-proof"><h3>静态符号绑定变化</h3><p>变更前：{finding.before_resolution.status} → {finding.before_resolution.target_symbol_id}</p><p>变更后：{finding.after_resolution.status} · {finding.after_resolution.reason}</p></div>}
          <details className="oi-evidence-metadata"><summary>证据元数据</summary><p>源码 SHA256：<code>{evidence?.source_hash || 'unavailable'}</code></p><DiagnosticsList diagnostics={evidence?.diagnostics} showEmptyState={false} /></details>
        </article><aside className="oi-explanation-panel"><h2>中文辅助解释</h2>{isUsableExplanation(explanation) ? <><p className="oi-explanation-summary">{explanation.summary}</p><p>{explanation.why_affected}</p><h3>建议检查</h3><p>{explanation.suggested_check}</p><p className="oi-explanation-note">规则说明 · 风险 {explanation.risk_level} · 置信度 {explanation.confidence}，不表示运行失败概率。</p></> : <div className="oi-report-unavailable"><b>Explanation unavailable</b><p>请直接查看静态证据与诊断。</p></div>}</aside></div>
      </div> : <div className="oi-report-empty" role="status"><span>∅</span><h2>当前没有确定影响</h2><p>{report.coverage.status === 'partial' ? '覆盖不完整，零结果不证明项目没有其他影响。' : '已支持范围内没有新增的符号引用断裂。'}</p><p>当前没有对应证据和解释，不使用 Demo 填充。</p></div>}
        <section className="oi-review-section"><h2>分析边界与诊断</h2><p>动态、遮蔽、重绑定、复杂作用域和无法解析的引用不升级为确定影响。</p><DiagnosticsList diagnostics={symbolDiagnosticEntries(report.diagnostics)} /></section>
      </div>
    </div>
  </section>;
}
