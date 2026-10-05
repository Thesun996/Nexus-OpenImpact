import SharedWorkflowSteps from '../components/WorkflowSteps.jsx';
import EmptyState from '../components/EmptyState.jsx';
import { diagnosticLabel, reasonLabel } from '../presentation/labels.js';

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
        : '项目模式：读取、校验和分析会重复上传本次选择的原始 ZIP，按项目指纹校验同一项目版本。刷新页面后需重新选择文件。'}
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
      <details><summary>技术详情</summary><code>{error.code}</code><p>{error.message}</p></details>
      {error.diagnostics && <DiagnosticsList diagnostics={error.diagnostics} showEmptyState={false} />}
    </section>
  );
}

export function CoverageNotice({ coverage }) {
  if (coverage?.status !== 'partial') return null;
  return (
    <section className="state-message" role="alert">
      <b>分析范围不完整。</b> {coverage.message || '部分源码或调用未解析，当前结果只覆盖能够确认的代码。'} 零条影响也不表示整个项目确定无影响；已经确定的影响仍可查看。
    </section>
  );
}

export function DiagnosticsList({ diagnostics, showEmptyState = true }) {
  const entries = Array.isArray(diagnostics)
    ? diagnostics.map((entry) => ({ category: 'diagnostic', entry }))
    : Object.entries(diagnostics || {}).flatMap(([category, values]) =>
      Array.isArray(values) ? values.map((entry) => ({ category, entry })) : []);
  if (!entries.length) return showEmptyState ? <p>未发现诊断项。</p> : null;
  return entries.map(({ category, entry }, index) => {
    const detail = typeof entry === 'object' && entry !== null ? entry : { message: String(entry) };
    return (
      <div className="diagnostic-item" key={`${category}-${index}`}>
        <b>{diagnosticLabel(detail.code || detail.kind || category)}{detail.file ? ` · ${detail.file}${detail.line != null ? `:${detail.line}` : ''}${detail.column != null ? `:${detail.column}` : ''}` : ''}</b>
        <span>{reasonLabel(detail.reason || detail.message)}</span>
        {detail.import_expression && <code>{detail.import_expression}</code>}
        <details><summary>技术详情</summary><p><code>{JSON.stringify(detail)}</code></p></details>
      </div>
    );
  });
}

export function EmptyWorkflow({ title, message, navigate }) {
  return (
    <EmptyState title={title} description={message} actionLabel="返回上传项目" onAction={() => navigate('upload')} />
  );
}
