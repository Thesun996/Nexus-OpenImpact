import { useEffect, useState } from 'react';
import { apiClient } from '../api/client.js';
import { formatTime } from './HistoryPage.jsx';
import { statusLabel } from '../components/report/presentation.js';

const PROJECT_PAGE_SIZE = 20;

export function projectSummary(snapshot) {
  if (!snapshot) return '暂无快照';
  return `Python 文件 ${snapshot.python_file_count ?? 0} · 函数 ${snapshot.function_count ?? 0} · 覆盖 ${statusLabel(snapshot.coverage_status)}`;
}

export function mergeProjects(current, incoming) {
  const seen = new Set(current.map((item) => item.id));
  return current.concat(incoming.filter((item) => !seen.has(item.id)));
}

export default function ProjectLibraryPage({ navigate }) {
  const [projects, setProjects] = useState([]);
  const [selected, setSelected] = useState(null);
  const [snapshots, setSnapshots] = useState([]);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState(null);
  const [hasMore, setHasMore] = useState(false);

  async function loadProjects(signal, preferredId = selected?.id, searchQuery = query) {
    setStatus('loading');
    setError(null);
    try {
      const payload = await apiClient.listProjects({ signal, limit: PROJECT_PAGE_SIZE, offset: 0, query: searchQuery });
      const items = Array.isArray(payload.items) ? payload.items : [];
      setProjects(items);
      setHasMore(payload.has_more === true);
      if (!items.length) {
        setSelected(null);
        setSnapshots([]);
        setStatus('ready');
        return;
      }
      const nextId = items.some((item) => item.id === preferredId) ? preferredId : items[0].id;
      await openProject(nextId, signal);
    } catch (failure) {
      if (failure?.name === 'AbortError') return;
      setError(failure?.message || '无法读取项目库，请检查后端服务。');
      setStatus('error');
    }
  }

  async function loadMoreProjects() {
    if (busy || !hasMore) return;
    setStatus('loading-more');
    setError(null);
    try {
      const payload = await apiClient.listProjects({ limit: PROJECT_PAGE_SIZE, offset: projects.length, query });
      const items = Array.isArray(payload.items) ? payload.items : [];
      setProjects((current) => mergeProjects(current, items));
      setHasMore(payload.has_more === true);
      setStatus('ready');
    } catch (failure) {
      if (failure?.name !== 'AbortError') {
        setError(failure?.message || '无法继续读取项目库。');
        setStatus('error');
      }
    }
  }

  async function openProject(id, signal) {
    setStatus('loading-detail');
    setError(null);
    try {
      const [project, snapshotPayload] = await Promise.all([
        apiClient.getProject(id, { signal }),
        apiClient.listProjectSnapshots(id, { signal, limit: PROJECT_PAGE_SIZE, offset: 0 }),
      ]);
      setSelected(project);
      setSnapshots(Array.isArray(snapshotPayload.items) ? snapshotPayload.items : []);
      setStatus('ready');
    } catch (failure) {
      if (failure?.name === 'AbortError') return;
      setError(failure?.message || '无法读取该项目快照。');
      setStatus('error');
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => void loadProjects(controller.signal, selected?.id, query), query ? 180 : 0);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [query]);

  const busy = status === 'loading' || status === 'loading-detail' || status === 'loading-more';
  const loadingMore = status === 'loading-more';

  return <div className="oi-history-page">
    <section className="page-heading">
      <div><h1>项目库</h1><p>读取本机 SQLite 中已保存的项目与 ZIP 快照；这是后端项目化基础，还不是账号级项目空间。</p></div>
      <div className="heading-actions">
        <span>{projects.length ? `已读取 ${projects.length} 个项目` : '暂无项目记录'}</span>
        <button className="ghost-action" type="button" onClick={() => void loadProjects(undefined, selected?.id, query)} disabled={busy}>刷新</button>
        <button className="ghost-action" type="button" onClick={() => navigate('upload')}>上传项目</button>
      </div>
    </section>
    <section className="state-message"><b>当前边界</b><p>项目库已经能保存 ZIP 快照和 Inspect 摘要，但当前分析流程仍要求重新上传 ZIP；基于项目 ID 重新分析需要后续接口确认后再接入。</p></section>
    {error && <section className="state-message error" role="alert">{error}</section>}
    <section className="oi-history-layout" aria-busy={busy}>
      <div className="oi-history-list" aria-label="已保存项目列表">
        <div className="oi-history-filter"><label htmlFor="oi-project-search">筛选项目</label><input id="oi-project-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="项目名、文件名、指纹…" /></div>
        {projects.length ? projects.map((project) => <article key={project.id} className={selected?.id === project.id ? 'oi-history-row is-selected' : 'oi-history-row'}>
          <button className="oi-history-open" type="button" onClick={() => void openProject(project.id)} disabled={busy}>
            <span><b>{project.name}</b><small>{formatTime(project.updated_at)}</small></span>
            <code>{project.latest_snapshot?.source_filename || '未记录上传文件'}</code>
            <span>{projectSummary(project.latest_snapshot)}</span>
          </button>
        </article>) : <div className="oi-history-empty"><b>{busy ? '正在读取项目库' : '还没有项目记录'}</b><p>{busy ? '正在从本地数据库读取项目摘要。' : '上传 ZIP 后可通过项目库接口保存项目记录；当前主流程仍可直接从上传页开始。'}</p></div>}
        {projects.length > 0 && hasMore ? <div className="oi-history-more"><button className="ghost-action" type="button" onClick={() => void loadMoreProjects()} disabled={busy}>{loadingMore ? '加载中…' : '加载更多'}</button></div> : null}
      </div>
      <div className="oi-history-detail">
        {selected ? <section className="detail-card">
          <h2>{selected.name}</h2>
          <dl className="impact-meta-grid">
            <div><dt>项目 ID</dt><dd><code>{selected.id}</code></dd></div>
            <div><dt>创建时间</dt><dd>{formatTime(selected.created_at)}</dd></div>
            <div><dt>更新时间</dt><dd>{formatTime(selected.updated_at)}</dd></div>
            <div><dt>最新快照</dt><dd>{projectSummary(selected.latest_snapshot)}</dd></div>
          </dl>
          <h3>快照记录</h3>
          <div className="oi-project-snapshots">
            {snapshots.length ? snapshots.map((snapshot) => <article key={snapshot.id} className="oi-project-snapshot">
              <div><b>{snapshot.source_filename || '未记录文件名'}</b><span>{formatTime(snapshot.created_at)}</span></div>
              <code>{snapshot.project_fingerprint}</code>
              <p>{projectSummary(snapshot)} · 源码根目录 {snapshot.analysis_root || '.'}</p>
            </article>) : <p>该项目暂无快照记录。</p>}
          </div>
        </section> : <section className="detail-card empty-state-card"><div className="empty-state-icon">∅</div><h2>{busy ? '正在读取项目库' : '未选择项目'}</h2><p>{busy ? '正在从本地数据库读取项目和快照。' : '左侧选择项目后查看快照摘要。'}</p></section>}
      </div>
    </section>
  </div>;
}
