import { DiagnosticsList } from '../../pages/PageParts.jsx';
import { entries, locationText, statusLabel, ruleLabel } from './presentation.js';

function Assessments({ title, items, manual, sectionRef }) {
  if (!items.length) return null;
  return <section ref={sectionRef} tabIndex={-1} className="oi-review-section" aria-label={title}>
    <header><h2>{title}</h2><span>{items.length} 条记录</span></header>
    <p>{manual ? '静态证据不足，需要人工检查；这些记录不计入确定直接影响，也不作为确定间接传播起点。' : '修改前已经存在的问题，不归因于本次变更，也不计入直接影响。'}</p>
    {items.map((item, index) => <div className="diagnostic-item" key={index}>
      <b>{item.caller_symbol_id || '调用方未提供'} → {item.target_symbol_id || '目标未提供'}</b>
      <span>位置：{locationText(item)}</span>
      <span>修改前：{statusLabel(item.before_status)} · {item.before_reason || '原因未提供'}</span>
      <span>修改后：{statusLabel(item.after_status)} · {item.after_reason || '原因未提供'}</span>
      {item.reason && <span>判断依据：{item.reason}</span>}
      {item.rule_id && <><span>规则：{ruleLabel(item.rule_id)}</span><details><summary>原始规则编号</summary><code>{item.rule_id}</code></details></>}
      {manual && <span>当前接口不为人工检查记录生成独立源码证据或辅助解释。</span>}
    </div>)}
  </section>;
}

export default function ReviewNotes({ report, sectionRefs }) {
  const calls = entries(report.diagnostics?.unresolved_calls);
  return <div className="oi-review-notes">
    <Assessments title="需要人工检查" items={entries(report.manual_reviews)} manual sectionRef={sectionRefs.manual} />
    <Assessments title="修改前已存在的问题" items={entries(report.pre_existing_problems)} sectionRef={sectionRefs.preexisting} />
    {!!calls.length && <section className="oi-review-section" ref={sectionRefs.unresolved} tabIndex={-1} aria-label="未解析调用详情">
      <header><h2>未能静态解析的调用</h2><span>{calls.length} 条记录</span></header>
      <p>未解析调用不作为确定影响或传播路径。这里只展示接口提供的语法事实及未解析原因。</p>
      <DiagnosticsList diagnostics={{ unresolved_calls: calls }} />
    </section>}
  </div>;
}

export function ReportDiagnostics({ report }) {
  // Calls already have their own indexed section above; do not repeat thousands
  // of the same records in the import/source diagnostics.
  const diagnostics = Object.fromEntries(Object.entries(report.diagnostics || {}).filter(([category]) => category !== 'unresolved_calls'));
  const count = Object.values(diagnostics).reduce((total, values) => total + entries(values).length, 0);
  return <details className="oi-report-diagnostics" open={count > 0 || report.coverage?.status === 'partial'}>
    <summary>诊断与分析范围 <span>{count} 条诊断记录</span></summary>
    <p>直接影响表示本次变更使原本兼容的调用变得不兼容。间接影响表示位于上游调用路径，建议检查；静态路径不保证运行时失败。</p>
    <p>覆盖模块：{report.coverage?.indexed_modules ?? '未提供'} · 覆盖函数：{report.coverage?.indexed_functions ?? '未提供'} · 解析失败文件：{report.coverage?.files_with_parse_errors ?? '未提供'}</p>
    {!!entries(report.diagnostics?.unresolved_calls).length && <p>未确认调用已在上方单独分组；下方为导入、源码与其他诊断。</p>}
    <DiagnosticsList diagnostics={diagnostics} />
  </details>;
}
