import { useEffect, useState } from 'react';
import { apiClient } from '../api/client.js';
import { ReportResults } from './ReportPage.jsx';
import { statusLabel } from '../components/report/presentation.js';

const HISTORY_PAGE_SIZE = 20;

export function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '时间未知';
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(date);
}

export function summaryText(summary) {
  const direct = summary?.direct_impact_count ?? summary?.direct_reference_count ?? summary?.import_impact_count ?? 0;
  const indirect = summary?.indirect_impact_count ?? summary?.symbol_indirect_impact_count ?? summary?.module_indirect_impact_count
    ?? ((summary?.indirect_1hop_count ?? 0) + (summary?.indirect_2hop_count ?? 0));
  const manual = summary?.manual_review_count ?? summary?.manual_review_required_count ?? 0;
  return `直接 ${direct} · 间接 ${indirect} · 人工检查 ${manual}`;
}

export function matchesHistoryQuery(record, query) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  const haystack = [
    record.project_name,
    record.source_filename,
    record.target_id,
    record.change_domain,
    record.change_type,
    record.coverage_status,
  ].filter(Boolean).join(' ').toLowerCase();
  return haystack.includes(normalized);
}

export function mergeHistoryRecords(current, incoming) {
  const seen = new Set(current.map((item) => item.id));
  return current.concat(incoming.filter((item) => !seen.has(item.id)));
}

export default function HistoryPage({ navigate }) {
  const [records, setRecords] = useState([]);
  const [selected, setSelected] = useState(null);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [query, setQuery] = useState('');
  const [hasMore, setHasMore] = useState(false);

  async function loadHistory(signal, preferredId = selected?.id, searchQuery = query) {
    setStatus('loading');
    setError(null);
    try {
      const payload = await apiClient.listReports({ signal, limit: HISTORY_PAGE_SIZE, offset: 0, query: searchQuery });
      const items = Array.isArray(payload.items) ? payload.items : [];
      setRecords(items);
      setHasMore(payload.has_more === true);
      if (!items.length) {
        setSelected(null);
        setStatus('ready');
        return;
      }
      const nextId = items.some((item) => item.id === preferredId) ? preferredId : items[0].id;
      const detail = await apiClient.getReport(nextId, { signal });
      setSelected(detail);
      setStatus('ready');
    } catch (failure) {
      if (failure?.name === 'AbortError') return;
      setError(failure?.message || '无法读取历史报告，请检查后端服务。');
      setStatus('error');
    }
  }

  async function loadMoreHistory() {
    if (status === 'loading-more' || busy || !hasMore) return;
    setStatus('loading-more');
    setError(null);
    try {
      const payload = await apiClient.listReports({ limit: HISTORY_PAGE_SIZE, offset: records.length, query });
      const items = Array.isArray(payload.items) ? payload.items : [];
      setRecords((current) => mergeHistoryRecords(current, items));
      setHasMore(payload.has_more === true);
      setStatus('ready');
    } catch (failure) {
      if (failure?.name !== 'AbortError') {
        setError(failure?.message || '无法继续读取历史报告。');
        setStatus('error');
      }
    }
  }

  async function openReport(id) {
    setStatus('loading-detail');
    setError(null);
    try {
      setSelected(await apiClient.getReport(id));
      setStatus('ready');
    } catch (failure) {
      if (failure?.name === 'AbortError') return;
      setError(failure?.message || '无法读取这条历史报告。');
      setStatus('error');
    }
  }

  async function deleteHistoryRecord(record) {
    if (!record?.id || deletingId) return;
    if (!window.confirm(`删除历史报告“${record.project_name || record.id}”？该操作只删除本机保存的报告，不会改动源码。`)) return;
    setDeletingId(record.id);
    setError(null);
    try {
      await apiClient.deleteReport(record.id);
      const remaining = records.filter((item) => item.id !== record.id);
      setRecords(remaining);
      if (selected?.id === record.id) {
        setSelected(null);
        if (remaining.length) await openReport(remaining[0].id);
      }
      setStatus('ready');
    } catch (failure) {
      if (failure?.name !== 'AbortError') {
        setError(failure?.message || '删除历史报告失败，请检查本地数据库。');
        setStatus('error');
      }
    } finally {
      setDeletingId(null);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => void loadHistory(controller.signal, selected?.id, query), query ? 180 : 0);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [query]);

  const busy = status === 'loading' || status === 'loading-detail' || status === 'loading-more';
  const loadingMore = status === 'loading-more';
  const visibleRecords = records.filter((record) => matchesHistoryQuery(record, query));

  return <div className="oi-history-page">
    <section className="page-heading">
      <div><h1>历史报告</h1><p>读取本机 SQLite 中已经保存的影响分析报告；这里只保存报告 JSON 和摘要，不保存上传 ZIP。</p></div>
      <div className="heading-actions">
        <span>{records.length ? `已读取 ${records.length} 条${query.trim() ? '匹配记录' : ''}` : '暂无历史记录'}</span>
        <button className="ghost-action" type="button" onClick={() => void loadHistory(undefined, selected?.id, query)} disabled={busy}>刷新</button>
        <button className="ghost-action" type="button" onClick={() => navigate('upload')}>返回上传</button>
      </div>
    </section>
    {error && <section className="state-message error" role="alert">{error}</section>}
    <section className="oi-history-layout" aria-busy={busy}>
      <div className="oi-history-list" aria-label="已保存报告列表">
        <div className="oi-history-filter"><label htmlFor="oi-history-search">筛选历史报告</label><input id="oi-history-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="项目、目标、变更类型…" /></div>
        {visibleRecords.length ? visibleRecords.map((record) => <article key={record.id} className={selected?.id === record.id ? 'oi-history-row is-selected' : 'oi-history-row'}>
          <button className="oi-history-open" type="button" onClick={() => void openReport(record.id)} disabled={busy || deletingId === record.id}>
            <span><b>{record.project_name}</b><small>{formatTime(record.created_at)}</small></span>
            <code>{record.target_id || '目标未提供'}</code>
            <span>{summaryText(record.summary)} · 覆盖 {statusLabel(record.coverage_status)}</span>
          </button>
          <button className="oi-history-delete" type="button" onClick={() => void deleteHistoryRecord(record)} disabled={busy || deletingId === record.id}>{deletingId === record.id ? '删除中…' : '删除'}</button>
        </article>) : <div className="oi-history-empty"><b>{records.length ? '没有匹配的历史报告' : '还没有保存过报告'}</b><p>{records.length ? '换一个项目名、目标函数或变更类型继续筛选。' : '完成一次实际项目分析后，在报告页点击“保存到历史”。'}</p></div>}
        {visibleRecords.length > 0 && hasMore ? <div className="oi-history-more"><button className="ghost-action" type="button" onClick={() => void loadMoreHistory()} disabled={busy}>{loadingMore ? '加载中…' : '加载更多'}</button></div> : null}
      </div>
      <div className="oi-history-detail">
        {selected?.report ? <ReportResults report={selected.report} mode="history" /> : <section className="detail-card empty-state-card"><div className="empty-state-icon">∅</div><h2>{busy ? '正在读取历史报告' : '未选择报告'}</h2><p>{busy ? '正在从本地数据库读取完整报告 JSON。' : '左侧选择一条报告后查看影响列表、证据和解释。'}</p></section>}
      </div>
    </section>
  </div>;
}
