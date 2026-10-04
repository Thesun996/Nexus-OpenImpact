import { DiagnosticsList } from '../../pages/PageParts.jsx';
import { entries, locationText } from './presentation.js';

function Assessments({ title, items, manual, sectionRef }) {
  if (!items.length) return null;
  return <section ref={sectionRef} tabIndex={-1} className="oi-review-section" aria-label={title}>
    <header><h2>{title}</h2><span>{items.length} 条记录</span></header>
    <p>{manual ? '静态证据不足，需要人工检查；这些记录不计入确定 Direct Impact，也不作为确定间接传播起点。' : '修改前已经存在的问题，不归因于本次 Change，也不计入 Direct Impact。'}</p>
    {items.map((item, index) => <div className="diagnostic-item" key={index}>
      <b>{item.caller_symbol_id || '调用方未提供'} → {item.target_symbol_id || '目标未提供'}</b>
      <span>位置：{locationText(item)}</span>
      <span>修改前：{item.before_status || '未提供'} · {item.before_reason || '原因未提供'}</span>
      <span>修改后：{item.after_status || '未提供'} · {item.after_reason || '原因未提供'}</span>
      {item.reason && <span>判断依据：{item.reason}</span>}
      {item.rule_id && <span>规则：<code>{item.rule_id}</code></span>}
      {manual && <span>当前 API 不为人工检查记录生成独立 Evidence 或 Explanation。</span>}
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
      <p>Unresolved：未解析调用不作为确定影响或传播路径。这里只展示接口提供的语法事实及未解析原因。</p>
      {calls.map((call, index) => <div className="diagnostic-item" key={index}><b>{locationText(call)}</b>
        <span>调用表达式：<code>{call.expression || '未提供'}</code></span><span>原因：{call.reason || '未提供'}</span>
      </div>)}
    </section>}
  </div>;
}

export function ReportDiagnostics({ report }) {
  const count = Object.values(report.diagnostics || {}).reduce((total, values) => total + entries(values).length, 0);
  return <details className="oi-report-diagnostics" open={count > 0 || report.coverage?.status === 'partial'}>
    <summary>诊断与分析范围 <span>{count} 条诊断记录</span></summary>
    <p>Direct 是本次变更造成的兼容性退化。Indirect 表示上游调用路径建议检查，静态路径不保证运行时失败。</p>
    <p>覆盖模块：{report.coverage?.indexed_modules ?? '未提供'} · 覆盖函数：{report.coverage?.indexed_functions ?? '未提供'} · 解析失败文件：{report.coverage?.files_with_parse_errors ?? '未提供'}</p>
    <DiagnosticsList diagnostics={report.diagnostics} />
  </details>;
}
