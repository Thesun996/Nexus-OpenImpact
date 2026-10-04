import { useState } from 'react';
import { useWorkflow } from '../state/WorkflowContext.jsx';
import { ErrorNotice, ModeNotice, WorkflowSteps } from './PageParts.jsx';

export default function UploadPage({ navigate }) {
  const { state, actions } = useWorkflow();
  const [dragging, setDragging] = useState(false);
  const busy = Object.values(state.loading).some(Boolean);
  const isDemo = state.mode === 'demo';
  const readStatus = isDemo ? '演示样例已就绪 · 保存的接口响应'
    : state.loading.inspect ? '正在上传 ZIP 并读取项目…'
      : state.inspect ? `读取完成 · ${state.inspect.symbols?.length ?? 0} 个函数`
        : state.file ? '文件已保留，等待 Inspect' : '等待选择 ZIP';

  async function inspectProject() {
    if (await actions.inspectProject()) navigate('functions');
  }

  async function openDemo() {
    if (await actions.loadDemo()) navigate('functions');
  }

  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) actions.selectFile(file);
  }

  return (
    <>
      <section className="page-heading">
        <div><h1>上传 Python ZIP</h1><p>准备一个小型 Python 项目。OpenImpact 只读取源码做静态分析。</p></div>
        <div className="heading-actions"><span>ZIP 上限 5 MiB</span><span className="mock-pill">{isDemo ? '独立演示模式' : 'Backend v1 · 真实 ZIP 分析'}</span></div>
      </section>
      <WorkflowSteps current={1} />
      <ModeNotice mode={state.mode} /><ErrorNotice error={state.error} />
      <section className="upload-grid">
        <article className="detail-card upload-card">
          <header><div className="detail-title"><b>▣</b> 选择 ZIP</div><mark className={`tag ${state.inspect ? 'low' : 'medium'}`}>{state.loading.inspect ? '读取中' : state.inspect ? isDemo ? '演示样例已就绪' : '项目已读取' : state.file ? '文件已保留，尚未读取' : '等待选择'}</mark></header>
          <label
            className={`upload-dropzone${dragging ? ' dragging' : ''}${state.file ? ' selected' : ''}`}
            onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
          >
            <input type="file" accept=".zip,application/zip,application/x-zip-compressed" aria-label="选择 Python 项目 ZIP"
              onChange={(event) => { const file = event.target.files?.[0]; if (file) actions.selectFile(file); event.target.value = ''; }} />
            <span className="upload-icon">▤</span><strong>选择 ZIP 文件</strong><small>拖放 ZIP 到这里，或点击选择文件</small>
          </label>
          <section className="upload-meta">
            <div><span>当前文件</span><b>{state.file?.name || '未选择文件'}</b></div>
            <div><span>文件大小</span><b>{state.file ? `${(state.file.size / 1024).toFixed(1)} KB` : '—'}</b></div>
            <div><span>读取状态</span><b>{readStatus}</b></div>
            <div><span>项目指纹</span><b style={{ overflowWrap: 'anywhere' }}>{state.projectFingerprint || 'Inspect 后生成 SHA-256'}</b></div>
            <div><span>文件生命周期</span><b>跨页面保留；刷新后需要重新选择</b></div>
          </section>
          <footer className="upload-actions"><span>{isDemo ? '演示样例与用户上传项目独立。选择新的 ZIP 将退出演示。' : 'Inspect、Validate、Analyze 使用同一原始 ZIP；重新选择文件将清除旧结果。'}</span>{isDemo ? <button className="primary-action" type="button" onClick={() => navigate('functions')}>查看演示函数</button> : <button className="primary-action" type="button" onClick={inspectProject} disabled={!state.file || busy}>{state.loading.inspect ? '正在读取项目…' : state.inspect ? '重新读取项目' : '读取真实项目'}</button>}</footer>
        </article>
        <aside className="detail-column upload-side-column">
          <article className="detail-card">
            <header><div className="detail-title"><b>✓</b> 第一版边界</div></header>
            <section className="info-list upload-boundary-list"><div><span>语言</span><b>Python</b></div><div><span>范围</span><b>模块级函数</b></div><div><span>变更</span><b>新增必填参数</b></div><div><span>判断</span><b>后端静态分析</b></div></section>
          </article>
          <article className="detail-card upload-note-card">
            <header><div className="detail-title"><b>▤</b> 独立演示项目</div><mark className="tag change">演示</mark></header>
            <p>使用仓库 signature_change 的脱敏接口样例预览页面。仅固定的 utils.format_date + timezone 变更可展示样例报告。</p>
            <div className="empty-state-actions"><button className="primary-action" type="button" onClick={openDemo} disabled={busy}>打开演示项目</button></div>
          </article>
        </aside>
      </section>
    </>
  );
}
