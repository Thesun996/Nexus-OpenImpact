import { useState } from 'react';
import { useWorkflow } from '../state/WorkflowContext.jsx';
import { CoverageNotice, ErrorNotice } from './PageParts.jsx';
import { ProjectDiagnostics, ProjectOverview, WorkflowNotes } from '../components/workflow/WorkflowParts.jsx';

export function UploadView({ state, dragging, onDragOver, onDragLeave, onDrop, onFileChange, onAnalysisRootChange, onInspect, onSaveProject, onOpenDemo, navigate }) {
  const busy = Object.values(state.loading).some(Boolean);
  const isDemo = state.mode === 'demo';
  const failed = state.error?.stage === 'inspect';
  const phase = state.loading.inspect ? 'loading' : state.inspect ? 'ready' : failed ? 'failed' : state.file ? 'selected' : 'unselected';
  const status = phase === 'loading' ? '正在上传 ZIP 并读取项目…' : phase === 'ready' ? isDemo ? '演示样例已就绪' : '项目已读取'
    : phase === 'failed' ? '读取未完成，请检查错误后重试' : phase === 'selected' ? '文件已保留，尚未读取' : '等待选择 ZIP';
  return <div className="oi-workflow-page oi-upload-page">
    <section className="page-heading"><div><h1>上传 Python ZIP</h1><p>从一份真实源码开始，追踪一次小改动的影响。</p></div><div className="heading-actions"><span>最大 5 MiB · .zip</span></div></section>
    <WorkflowNotes current={1} mode={state.mode} /><ErrorNotice error={state.error} /><CoverageNotice coverage={state.inspect?.coverage} compact />
    <section className="oi-upload-workspace">
      <article className="oi-upload-surface" aria-label="项目 ZIP" aria-busy={state.loading.inspect}>
        <header><h2>选择项目文件</h2><p role="status" data-upload-state={phase} className={`oi-upload-status is-${phase}`}>{status}</p></header>
        <label className={`oi-zip-dropzone${dragging ? ' is-dragging' : ''}`} onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}>
          <input type="file" accept=".zip,application/zip,application/x-zip-compressed" aria-label="选择 Python 项目 ZIP" onChange={onFileChange} />
          <span className="oi-zip-mark" aria-hidden="true">.zip</span><strong>{state.file ? '选择另一份 ZIP' : '选择 ZIP 文件'}</strong><span>拖放到这里，或点击选择</span>
        </label>
        <dl className="oi-file-facts"><div><dt>当前文件</dt><dd>{state.file?.name || state.snapshot?.source_filename || '未选择文件'}</dd></div><div><dt>{state.snapshot ? '项目来源' : '文件大小'}</dt><dd>{state.snapshot ? '已保存快照' : state.file ? `${(state.file.size / 1024).toFixed(1)} KB` : '—'}</dd></div></dl>
        <div className="oi-source-root"><label htmlFor="analysis-root">源码根目录</label><input id="analysis-root" value={state.analysisRoot ?? '.'} onChange={(event) => onAnalysisRootChange?.(event.target.value)} disabled={isDemo || !!state.snapshot} spellCheck={false} autoComplete="off" aria-describedby="analysis-root-help" />
          <p id="analysis-root-help">普通项目保留 <code>.</code>；采用 src 布局的项目填写 <code>src</code>。路径相对于解包后的项目目录，请选择 Python 包的父目录。更改后需重新读取，原选择、校验和报告会失效。</p></div>
        <p className="oi-file-lifecycle">{isDemo ? '选择新的 ZIP 将退出演示。' : state.snapshot ? '当前使用已保存快照，刷新后可以从项目库重新打开。' : '直接读取只保留当前会话；开始分析时会自动保存当前 ZIP 快照，也可提前保存到项目库。'} 更换 ZIP 会清除原项目的选择、校验和报告。</p>
        <footer className="oi-upload-actions"><span>{state.inspect ? '项目已就绪' : '等待读取项目'}</span>{isDemo ? <button className="primary-action" type="button" onClick={() => navigate('functions')}>查看演示函数</button> : <><button className="ghost-action" type="button" onClick={onInspect} disabled={(!state.file && !state.snapshot) || busy}>{state.loading.inspect ? '正在读取项目…' : state.inspect ? '重新读取项目' : '读取真实项目'}</button>{!state.snapshot && <button className="primary-action" type="button" onClick={onSaveProject} disabled={!state.file || busy}>保存并读取项目</button>}</>}</footer>
        {state.inspect && <div className="oi-upload-result"><ProjectOverview inspect={state.inspect} file={state.file} snapshot={state.snapshot} fingerprint={state.projectFingerprint} mode={state.mode} /><button className="ghost-action" type="button" onClick={() => navigate('functions')} disabled={busy}>继续选择分析目标</button><ProjectDiagnostics diagnostics={state.inspect.diagnostics} coverage={state.inspect.coverage} /></div>}
      </article>
      <aside className="oi-upload-context" aria-label="支持范围与独立演示"><section><h2>这次可以分析什么</h2><p>Python 模块级函数：新增、删除、重命名参数，或将可选参数改为必填。</p><p>另支持根目录 Python 模块重命名或拟定删除，追踪明确静态导入。</p><p>公开模块变量与常量可拟定重命名或删除，追踪明确静态符号引用。</p><p>源码只用于静态分析；上传代码不会执行，也不会被自动修改。</p></section><section className="oi-demo-entry"><h2>先了解分析结果</h2><p>独立演示使用 signature_change 的固定接口样例，与实际上传项目分开。</p><button className="ghost-action" type="button" onClick={onOpenDemo} disabled={busy}>打开演示项目</button></section></aside>
    </section>
  </div>;
}

export default function UploadPage({ navigate }) {
  const { state, actions } = useWorkflow();
  const [dragging, setDragging] = useState(false);
  async function inspectProject() { if (await actions.inspectProject()) navigate('functions'); }
  async function saveProject() { if (await actions.saveProject()) navigate('functions'); }
  async function openDemo() { if (await actions.loadDemo()) navigate('functions'); }
  function handleDrop(event) { event.preventDefault(); setDragging(false); const file = event.dataTransfer.files?.[0]; if (file) actions.selectFile(file); }
  return <UploadView state={state} dragging={dragging} navigate={navigate} onInspect={inspectProject} onSaveProject={saveProject} onOpenDemo={openDemo}
    onAnalysisRootChange={(value) => actions.setAnalysisRoot(value)}
    onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={handleDrop}
    onFileChange={(event) => { const file = event.target.files?.[0]; if (file) actions.selectFile(file); event.target.value = ''; }} />;
}
