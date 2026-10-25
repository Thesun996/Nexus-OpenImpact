import SharedWorkflowSteps from '../components/WorkflowSteps.jsx';
import EmptyState from '../components/EmptyState.jsx';
import { diagnosticLabel, reasonLabel } from '../presentation/labels.js';
import { diagnosticEntries, groupDiagnostics } from '../presentation/diagnostics.js';
import '../presentation/diagnostics.css';

export function WorkflowSteps({ current }) {
  return <SharedWorkflowSteps page={['upload', 'functions', 'change', 'report'][current - 1]} />;
}

export function ModeNotice({ mode }) {
  return (
    <details className="oi-workflow-note">
      <summary>{mode === 'demo' ? '演示文件说明' : '项目文件与会话说明'}</summary>
      <p>
      {mode === 'demo'
        ? '演示模式：当前展示仓库 signature_change 的固定接口样例。结果只属于演示文件，未请求真实分析接口。'
        : '项目模式：按项目指纹校验同一项目版本。直接读取的 ZIP 保留在当前会话；已保存的项目可以从项目库重新打开。'}
      </p>
    </details>
  );
}

export function ErrorNotice({ error }) {
  if (!error) return null;
  return (
    <section className="state-message error" role="alert">
      <b>{diagnosticLabel(error.code)}</b>：{reasonLabel(error.message)}
      {error.code === 'fingerprint_mismatch' && <p>本次 ZIP 与此前读取的项目指纹不一致，已清除旧项目结果。请<a href="#upload">返回上传页</a>重新读取当前 ZIP，再选择目标并校验变更。</p>}
      {error.code === 'task_wait_timeout' && <p>任务已保留在本机任务库中，但在等待时间内没有完成。请确认后端与本机 Worker 都已启动，再点击“继续查询”或前往<a href="#tasks">分析任务</a>刷新状态。</p>}
      <details><summary>技术详情</summary><code>{error.code}</code><p>{error.message}</p></details>
      {error.diagnostics && <DiagnosticsList diagnostics={error.diagnostics} showEmptyState={false} />}
    </section>
  );
}

export function CoverageNotice({ coverage, compact = false }) {
  if (coverage?.status !== 'partial') return null;
  const { python_files: files, parsed_python_files: parsed } = coverage.details || {};
  const missingSources = Number.isSafeInteger(files) && Number.isSafeInteger(parsed) && parsed >= 0 && files > parsed ? files - parsed : 0;
  const details = <details className="oi-coverage-notice">
    <summary><b>分析详情</b><span>{missingSources ? `${missingSources} 个文件未解析` : '部分关系待确认'}</span><small>展开查看</small></summary>
    <div>
      {coverage.message && <p>{coverage.message}</p>}
      <p>零条确定影响仅适用于当前可确认范围，不能据此判断整个项目无影响。</p>
      <CoverageDetails coverage={coverage} />
    </div>
  </details>;
  if (compact) return details;
  return (
    <section className="oi-coverage-summary" aria-label="分析范围">
      <p>结果基于已确认的代码关系，未确认部分可在「分析详情」查看。</p>
      {details}
    </section>
  );
}

export function CoverageDetails({ coverage }) {
  const details = coverage?.details;
  if (!details) return null;
  const count = (value) => Number.isSafeInteger(value) && value >= 0;
  return <>
    {count(details.parsed_python_files) && count(details.python_files) &&
      <p>源码解析：{details.parsed_python_files} / {details.python_files} 个 Python 文件成功解析。源码解析成功不代表所有调用关系均已确认。</p>}
    {count(details.resolved_call_count) && count(details.unresolved_call_count) &&
      <p>调用关系：已确认 {details.resolved_call_count} 处，尚未确认 {details.unresolved_call_count} 处。未确认的记录包含外部依赖、对象方法与动态调用，数量不等于本次变更的漏检数。</p>}
    {count(details.excluded_call_count) && details.excluded_call_count > 0 &&
      <p>另有 {details.excluded_call_count} 个调用处于暂未支持的作用域，请查看下方诊断。类方法与嵌套函数中对明确模块级函数的调用已纳入检查。</p>}
  </>;
}

function DiagnosticItem({ category, detail }) {
  return <div className="diagnostic-item">
    <b>{diagnosticLabel(detail.code || detail.kind || category)}{detail.file ? ` · ${detail.file}${detail.line != null ? `:${detail.line}` : ''}${detail.column != null ? `:${detail.column}` : ''}` : ''}</b>
    <span>{reasonLabel(detail.reason || detail.message)}</span>
    {detail.expression && <span>调用或引用表达式：<code>{detail.expression}</code></span>}
    {detail.import_expression && <code>{detail.import_expression}</code>}
    {detail.local_name && <span>本地绑定名称：<code>{detail.local_name}</code></span>}
    <details><summary>技术详情</summary><p><code>{JSON.stringify(detail)}</code></p></details>
  </div>;
}

export function DiagnosticsList({ diagnostics, showEmptyState = true, grouped = !Array.isArray(diagnostics) }) {
  const entries = diagnosticEntries(diagnostics);
  if (!entries.length) return showEmptyState ? <p>未发现诊断项。</p> : null;
  const renderEntries = items => items.map((item, index) => <DiagnosticItem {...item} key={`${item.category}-${index}`} />);
  // Validation/error arrays remain immediately visible. Project diagnostics
  // use native disclosures: no animation or keyboard interaction dependency.
  if (!grouped) return renderEntries(entries);
  return <div className="oi-diagnostic-groups">
    <p>按未确认原因分组，展开查看位置与检查说明。分组不改变影响数量或覆盖结论，也不代表这些记录都与本次变更有关。</p>
    {groupDiagnostics(entries).map(group => <details className="oi-diagnostic-group" key={group.id}
      open={group.entries.some(({ category, detail }) => ['parse_errors', 'parse_diagnostics', 'syntax_diagnostics'].includes(category)
        || ['syntax_error', 'SyntaxError', 'read_error', 'encoding_error'].includes(detail.kind || detail.code))}>
      <summary><b>{group.title}</b><span>{group.entries.length} 条记录</span></summary>
      <p>{group.description}</p>{renderEntries(group.entries)}
    </details>)}
  </div>;
}

export function EmptyWorkflow({ title, message, navigate }) {
  return (
    <EmptyState title={title} description={message} actionLabel="返回上传项目" onAction={() => navigate('upload')} />
  );
}
