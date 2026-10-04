import SharedWorkflowSteps from '../components/WorkflowSteps.jsx';
import EmptyState from '../components/EmptyState.jsx';

export function WorkflowSteps({ current }) {
  return <SharedWorkflowSteps page={['upload', 'functions', 'change', 'report'][current - 1]} />;
}

export function ModeNotice({ mode }) {
  return (
    <section className="state-message" role="note">
      {mode === 'demo'
        ? '演示模式：当前展示仓库 signature_change 的固定接口样例。结果只属于演示文件，未请求真实分析接口。'
        : '项目模式：Inspect、Validate、Analyze 会重复上传本次选择的原始 ZIP，按 Inspect 指纹校验同一项目版本。刷新页面后需重新选择文件。'}
    </section>
  );
}

export function ErrorNotice({ error }) {
  if (!error) return null;
  return (
    <section className="state-message error" role="alert">
      <b>{error.code || '操作未完成'}</b>：{error.message}
      {error.code === 'fingerprint_mismatch' && <p>本次 ZIP 与此前 Inspect 的 project_fingerprint 不一致，已清除旧项目结果。请<a href="#upload">返回上传页</a>重新读取当前 ZIP，再选择函数并校验变更。</p>}
      {error.diagnostics && <DiagnosticsList diagnostics={error.diagnostics} />}
    </section>
  );
}

export function CoverageNotice({ coverage }) {
  if (coverage?.status !== 'partial') return null;
  return (
    <section className="state-message" role="alert">
      <b>partial：分析范围不完整。</b> {coverage.message || '部分源码或调用未解析，当前结果只覆盖能够确认的代码。'} 零条影响也不表示整个项目确定无影响；已经确定的影响仍可查看。
    </section>
  );
}

export function DiagnosticsList({ diagnostics }) {
  const entries = Array.isArray(diagnostics)
    ? diagnostics.map((entry) => ({ category: 'diagnostic', entry }))
    : Object.entries(diagnostics || {}).flatMap(([category, values]) =>
      Array.isArray(values) ? values.map((entry) => ({ category, entry })) : []);
  if (!entries.length) return <p>未发现诊断项。</p>;
  return entries.map(({ category, entry }, index) => {
    const detail = typeof entry === 'object' && entry !== null ? entry : { message: String(entry) };
    return (
      <div className="diagnostic-item" key={`${category}-${index}`}>
        <b>{detail.code || detail.kind || category}{detail.file ? ` · ${detail.file}${detail.line != null ? `:${detail.line}` : ''}${detail.column != null ? `:${detail.column}` : ''}` : ''}</b>
        <span>{detail.message || detail.reason || JSON.stringify(detail)}</span>
      </div>
    );
  });
}

export function EmptyWorkflow({ title, message, navigate }) {
  return (
    <EmptyState title={title} description={message} actionLabel="返回上传项目" onAction={() => navigate('upload')} />
  );
}
