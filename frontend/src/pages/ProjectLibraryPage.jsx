import { useEffect, useRef, useState } from 'react';
import { apiClient } from '../api/client.js';
import { useWorkflow } from '../state/WorkflowContext.jsx';
import { createRequestGate } from '../components/workspace/requestGate.js';
import { formatTime } from './HistoryPage.jsx';
import { ErrorNotice } from './PageParts.jsx';
import { statusLabel } from '../components/report/presentation.js';

const PROJECT_PAGE_SIZE = 20;

export function projectSummary(snapshot) {
  if (!snapshot) return '暂无快照';
  return `Python 文件 ${snapshot.python_file_count ?? '未知'} · 函数 ${snapshot.function_count ?? '未知'} · 覆盖 ${statusLabel(snapshot.coverage_status)}`;
}

export function mergeProjects(current, incoming) {
  const seen = new Set();
  return [...current, ...incoming].filter(item => !seen.has(item.id) && seen.add(item.id));
}

export default function ProjectLibraryPage({ navigate }) {
  const { state, actions } = useWorkflow();
  const [projects, setProjects] = useState([]);
  const [selected, setSelected] = useState(null);
  const [snapshots, setSnapshots] = useState([]);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [snapshotHasMore, setSnapshotHasMore] = useState(false);
  const gate = useRef(createRequestGate());
  const offset = useRef(0);
  const latestQuery = useRef(query); latestQuery.current = query;
  const mounted = useRef(true);
  const openSequence = useRef(0);
  const deletePending = useRef(false);
  const busy = status.startsWith('loading') || state.loading.inspect || !!deletingId;

  async function readProject(id, request) {
    const [project, payload] = await Promise.all([
      apiClient.getProject(id, { signal: request.controller.signal }),
      apiClient.listProjectSnapshots(id, { signal: request.controller.signal, limit: PROJECT_PAGE_SIZE }),
    ]);
    if (!gate.current.current(request)) return;
    if (project.id !== id || !Array.isArray(payload.items) || payload.items.some(item => item.project_id !== id))
      throw new Error('项目快照响应不匹配，请刷新项目库。');
    setSelected(project); setSnapshots(payload.items); setSnapshotHasMore(payload.has_more === true);
  }

  async function loadProjects(append = false, search = query) {
    const request = gate.current.begin();
    setStatus(append ? 'loading-more' : 'loading'); setError(null);
    if (!append) { setSelected(null); setSnapshots([]); setProjects([]); }
    try {
      const payload = await apiClient.listProjects({ signal: request.controller.signal,
        limit: PROJECT_PAGE_SIZE, offset: append ? offset.current : 0, query: search });
      if (!gate.current.current(request) || latestQuery.current !== search) return;
      if (!Array.isArray(payload.items)) throw new Error('项目列表响应不完整，请重试。');
      const items = payload.items;
      offset.current = (append ? offset.current : 0) + items.length;
      setProjects(current => append ? mergeProjects(current, items) : items);
      setHasMore(payload.has_more === true);
      if (!append && items.length) await readProject(items[0].id, request);
    } catch (failure) {
      if (gate.current.current(request) && failure.name !== 'AbortError') setError(failure.message || '无法读取项目库。');
    } finally {
      if (gate.current.current(request)) setStatus('ready');
    }
  }

  async function openProject(id) {
    const request = gate.current.begin();
    setStatus('loading-detail'); setError(null); setSelected(null); setSnapshots([]);
    try { await readProject(id, request); }
    catch (failure) {
      if (gate.current.current(request) && failure.name !== 'AbortError') setError(failure.message || '无法读取该项目。');
    } finally { if (gate.current.current(request)) setStatus('ready'); }
  }

  async function loadMoreSnapshots() {
    if (busy || !selected || !snapshotHasMore) return;
    const request = gate.current.begin();
    setStatus('loading-snapshots'); setError(null);
    try {
      const payload = await apiClient.listProjectSnapshots(selected.id, {
        signal: request.controller.signal, limit: PROJECT_PAGE_SIZE, offset: snapshots.length,
      });
      if (!gate.current.current(request)) return;
      if (!Array.isArray(payload.items) || payload.items.some(item => item.project_id !== selected.id))
        throw new Error('项目快照响应不匹配，请刷新项目库。');
      setSnapshots(current => mergeProjects(current, payload.items)); setSnapshotHasMore(payload.has_more === true);
    } catch (failure) {
      if (gate.current.current(request) && failure.name !== 'AbortError') setError(failure.message);
    } finally { if (gate.current.current(request)) setStatus('ready'); }
  }

  async function analyzeSnapshot(snapshot) {
    const sequence = ++openSequence.current;
    if (await actions.openSnapshot(snapshot)) {
      if (mounted.current && openSequence.current === sequence) navigate('functions');
    }
  }

  async function deleteLibraryProject(project) {
    if (!project?.id || busy || deletePending.current) return;
    if (!window.confirm(`删除项目“${project.name || project.id}”？该操作只删除本机项目库记录和未被其他项目引用的 ZIP 快照，不会改动源码仓库。`)) return;
    deletePending.current = true;
    const request = gate.current.begin();
    setDeletingId(project.id); setError(null);
    try {
      try { await apiClient.deleteProject(project.id, { signal: request.controller.signal }); }
      catch (failure) { if (failure?.status !== 404) throw failure; }
      if (!gate.current.current(request)) return;
      await loadProjects(false, query);
    } catch (failure) {
      if (gate.current.current(request) && failure.name !== 'AbortError') setError(failure.message || '删除项目失败。');
    } finally {
      deletePending.current = false;
      if (mounted.current) setDeletingId(null);
    }
  }

  async function deleteSnapshot(snapshot) {
    if (!selected?.id || !snapshot?.id || busy || deletePending.current) return;
    if (!window.confirm(`删除快照“${snapshot.source_filename || snapshot.id}”？该操作只删除本机快照记录和未被其他项目引用的 ZIP 文件。`)) return;
    deletePending.current = true;
    const request = gate.current.begin();
    setDeletingId(snapshot.id); setError(null);
    try {
      let payload = null;
      try { payload = await apiClient.deleteProjectSnapshot(selected.id, snapshot.id, { signal: request.controller.signal }); }
      catch (failure) { if (failure?.status !== 404) throw failure; }
      if (!gate.current.current(request)) return;
      if (payload?.project_deleted) await loadProjects(false, query);
      else await readProject(selected.id, request);
    } catch (failure) {
      if (gate.current.current(request) && failure.name !== 'AbortError') setError(failure.message || '删除项目快照失败。');
    } finally {
      deletePending.current = false;
      if (mounted.current) setDeletingId(null);
      if (gate.current.current(request)) setStatus('ready');
    }
  }

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; openSequence.current++; gate.current.cancel(); };
  }, []);
  useEffect(() => {
    gate.current.cancel(); setStatus('loading'); setSelected(null); setSnapshots([]); setProjects([]);
    const timeout = window.setTimeout(() => void loadProjects(false, query), query ? 180 : 0);
    return () => { window.clearTimeout(timeout); gate.current.cancel(); };
  }, [query]);

  return <div className="oi-history-page oi-project-library">
    <section className="page-heading">
      <div><h1>项目库</h1><p>本机已保存的项目</p></div>
      <div className="heading-actions">
        <span>{projects.length ? `已读取 ${projects.length} 个项目` : ''}</span>
        <button className="ghost-action" type="button" onClick={() => void loadProjects()} disabled={busy}>刷新</button>
        <button className="ghost-action" type="button" onClick={() => navigate('upload')}>上传项目</button>
      </div>
    </section>
    {error && <section className="state-message error" role="alert">{error}</section>}
    <ErrorNotice error={state.error?.stage === 'inspect' ? state.error : null} />
    <section className="oi-history-layout" aria-busy={busy}>
      <div className="oi-history-list" aria-label="已保存项目列表">
        <div className="oi-history-filter"><label htmlFor="oi-project-search">筛选项目</label><input id="oi-project-search" type="search" maxLength={80} disabled={!!deletingId || state.loading.inspect} value={query} onChange={(event) => { gate.current.cancel(); setQuery(event.target.value); }} placeholder="项目名、文件名、指纹…" /></div>
        {projects.length ? projects.map((project) => <article key={project.id} className={selected?.id === project.id ? 'oi-history-row is-selected' : 'oi-history-row'}>
          <button className="oi-history-open" type="button" aria-pressed={selected?.id === project.id} onClick={() => void openProject(project.id)} disabled={busy}>
            <span><b>{project.name}</b><small>{formatTime(project.updated_at)}</small></span>
            <code>{project.latest_snapshot?.source_filename || '未记录上传文件'}</code>
            <span>{projectSummary(project.latest_snapshot)}</span>
          </button>
          <button className="oi-history-delete" type="button" onClick={() => void deleteLibraryProject(project)} disabled={busy}>{deletingId === project.id ? '删除中…' : '删除'}</button>
        </article>) : <div className="oi-history-empty" role="status"><b>{busy ? '正在读取项目库' : error ? '项目库暂时不可用' : query.trim() ? '没有匹配的项目' : '还没有保存的项目'}</b></div>}
        {projects.length > 0 && hasMore && <div className="oi-history-more"><button className="ghost-action" type="button" onClick={() => void loadProjects(true)} disabled={busy}>{status === 'loading-more' ? '加载中…' : '加载更多'}</button></div>}
      </div>
      <div className="oi-history-detail">
        {selected ? <section className="oi-project-detail">
          <h2>{selected.name}</h2>
          <dl className="oi-project-facts">
            <div><dt>创建时间</dt><dd>{formatTime(selected.created_at)}</dd></div>
            <div><dt>更新时间</dt><dd>{formatTime(selected.updated_at)}</dd></div>
            <div><dt>最新快照</dt><dd>{projectSummary(selected.latest_snapshot)}</dd></div>
          </dl>
          <h3>快照记录</h3>
          <div className="oi-project-snapshots">
            {snapshots.map((snapshot) => <article key={snapshot.id} className="oi-project-snapshot">
              <div><b>{snapshot.source_filename || '未记录文件名'}</b><span>{formatTime(snapshot.created_at)}</span></div>
              <p>{projectSummary(snapshot)} · 源码根目录 {snapshot.analysis_root || '.'}</p>
              <details><summary>快照指纹</summary><code>{snapshot.project_fingerprint}</code></details>
              <div className="oi-project-snapshot-actions">
                <button type="button" className="primary-action" disabled={busy} onClick={() => void analyzeSnapshot(snapshot)}>{state.loading.inspect && state.snapshot?.id === snapshot.id ? '正在读取快照…' : '使用此快照分析'}</button>
                <button type="button" className="ghost-action" disabled={busy} onClick={() => void deleteSnapshot(snapshot)}>{deletingId === snapshot.id ? '删除中…' : '删除快照'}</button>
              </div>
            </article>)}
            {snapshotHasMore && <button type="button" className="ghost-action" disabled={busy} onClick={() => void loadMoreSnapshots()}>更多快照</button>}
          </div>
        </section> : <section className="oi-project-detail" role="status"><h2>{busy ? '正在读取项目' : '未选择项目'}</h2></section>}
      </div>
    </section>
  </div>;
}
