import { useEffect, useRef, useState } from 'react';
import { apiClient } from '../api/client.js';
import { useWorkflow } from '../state/WorkflowContext.jsx';
import { createRequestGate } from '../components/workspace/requestGate.js';
import { WithoutProjectSource } from '../components/workspace/SourceWorkspace.jsx';
import { ErrorNotice } from './PageParts.jsx';
import { ReportResults } from './ReportPage.jsx';
import { statusLabel } from '../components/report/presentation.js';
import ReportDownload from '../components/report/ReportDownload.jsx';

const HISTORY_PAGE_SIZE = 20;

export function formatTime(value) {
  if (!value) return '时间未知';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '时间未知';
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(date);
}

export function summaryText(summary) {
  const count = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
  const direct = count(summary?.direct_impact_count ?? summary?.direct_reference_count
    ?? summary?.direct_import_count ?? summary?.import_impact_count);
  const hop1 = count(summary?.indirect_1hop_count ?? summary?.indirect_1hop_module_count);
  const hop2 = count(summary?.indirect_2hop_count ?? summary?.indirect_2hop_module_count);
  const indirect = count(summary?.indirect_impact_count ?? summary?.symbol_indirect_impact_count
    ?? summary?.module_indirect_impact_count ?? (hop1 !== null && hop2 !== null ? hop1 + hop2 : null));
  const manual = count(summary?.manual_review_count ?? summary?.manual_review_required_count);
  return `直接 ${direct ?? '未知'} · 间接 ${indirect ?? '未知'} · 人工检查 ${manual ?? '未知'}`;
}

export function matchesHistoryQuery(record, query) {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const haystack = [record.project_name, record.source_filename, record.target_id,
    record.change_domain, record.change_type, record.coverage_status].filter(Boolean).join(' ').toLowerCase();
  return terms.every(term => haystack.includes(term));
}

export function mergeHistoryRecords(current, incoming) {
  const seen = new Set();
  return [...current, ...incoming].filter(item => !seen.has(item.id) && seen.add(item.id));
}

export function reportSnapshot(record) {
  const report = record?.report;
  if (!/^[a-f0-9]{32}$/.test(report?.project_id) || !/^[a-f0-9]{32}$/.test(report?.project_snapshot_id)
    || !/^[a-f0-9]{64}$/.test(record?.project_fingerprint) || report.project_fingerprint !== record.project_fingerprint
    || typeof record.analysis_root !== 'string'
    || (report.analysis_layout?.analysis_root ?? '.') !== record.analysis_root) return null;
  return { id: report.project_snapshot_id, project_id: report.project_id,
    project_fingerprint: record.project_fingerprint, analysis_root: record.analysis_root,
    source_filename: record.source_filename };
}

export default function HistoryPage({ navigate }) {
  const { state, actions } = useWorkflow();
  const [records, setRecords] = useState([]);
  const [selected, setSelected] = useState(null);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [query, setQuery] = useState('');
  const [hasMore, setHasMore] = useState(false);
  const [openingSource, setOpeningSource] = useState(false);
  const gate = useRef(createRequestGate());
  const offset = useRef(0);
  const deletePending = useRef(false);
  const mounted = useRef(true);
  const latestQuery = useRef(query); latestQuery.current = query;
  const busy = status.startsWith('loading') || !!deletingId || state.loading.inspect;
  const snapshot = reportSnapshot(selected);

  function failure(request, reason, message) {
    if (!gate.current.current(request) || reason?.name === 'AbortError') return;
    setError(reason?.message || message); setStatus('error');
  }

  async function readDetail(id, request) {
    const detail = await apiClient.getReport(id, { signal: request.controller.signal });
    if (!gate.current.current(request)) return;
    if (detail.id !== id || !detail.report) throw new Error('历史报告响应不匹配，请重新读取。');
    setSelected(detail);
  }

  async function loadHistory(search = query, preferredId = selected?.id) {
    const request = gate.current.begin();
    setStatus('loading'); setError(null); setSelected(null); setRecords([]); setHasMore(false);
    try {
      const payload = await apiClient.listReports({ signal: request.controller.signal, limit: HISTORY_PAGE_SIZE, offset: 0, query: search });
      if (!gate.current.current(request) || latestQuery.current !== search) return;
      if (!Array.isArray(payload.items)) throw new Error('历史列表响应不完整，请重新读取。');
      const items = payload.items;
      setRecords(items); offset.current = items.length; setHasMore(payload.has_more === true);
      if (items.length) await readDetail(items.some(item => item.id === preferredId) ? preferredId : items[0].id, request);
      if (gate.current.current(request)) setStatus('ready');
    } catch (reason) { failure(request, reason, '无法读取历史报告。'); }
  }

  async function loadMoreHistory() {
    if (busy || !hasMore) return;
    const request = gate.current.begin();
    setStatus('loading-more'); setError(null);
    try {
      const payload = await apiClient.listReports({ signal: request.controller.signal,
        limit: HISTORY_PAGE_SIZE, offset: offset.current, query });
      if (!gate.current.current(request)) return;
      if (!Array.isArray(payload.items)) throw new Error('历史列表响应不完整，请重新读取。');
      offset.current += payload.items.length;
      setRecords(current => mergeHistoryRecords(current, payload.items));
      setHasMore(payload.has_more === true); setStatus('ready');
    } catch (reason) { failure(request, reason, '无法继续读取历史报告。'); }
  }

  async function openReport(id) {
    const request = gate.current.begin();
    setStatus('loading-detail'); setError(null); setSelected(null); setOpeningSource(false);
    try {
      await readDetail(id, request);
      if (gate.current.current(request)) setStatus('ready');
    } catch (reason) { failure(request, reason, '无法读取这条历史报告。'); }
  }

  async function deleteHistoryRecord(record) {
    if (!record?.id || deletePending.current || busy) return;
    if (!window.confirm(`删除历史报告“${record.project_name || record.id}”？该操作只删除本机保存的报告，不会改动源码。`)) return;
    deletePending.current = true;
    const request = gate.current.begin();
    setDeletingId(record.id); setError(null);
    try {
      try { await apiClient.deleteReport(record.id, { signal: request.controller.signal }); }
      catch (reason) { if (reason?.status !== 404) throw reason; }
      if (!gate.current.current(request)) return;
      // Deletion shifts offset pagination. Reload the first page to avoid skipping records.
      await loadHistory(query, selected?.id === record.id ? null : selected?.id);
    } catch (reason) { failure(request, reason, '删除历史报告失败。'); }
    finally {
      deletePending.current = false;
      if (mounted.current) setDeletingId(null);
    }
  }

  async function openSourceProject() {
    if (!snapshot || busy) return;
    setOpeningSource(true);
    if (await actions.openSnapshot(snapshot)) {
      if (mounted.current) navigate('functions');
    }
  }

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; gate.current.cancel(); };
  }, []);
  useEffect(() => {
    gate.current.cancel(); setSelected(null); setRecords([]); setStatus('loading');
    const timeout = window.setTimeout(() => void loadHistory(query, null), query ? 180 : 0);
    return () => { window.clearTimeout(timeout); gate.current.cancel(); };
  }, [query]);

  return <div className="oi-history-page">
    <section className="page-heading">
      <div><h1>历史报告</h1><p>本机已保存的影响分析报告</p></div>
      <div className="heading-actions">
        <span>{records.length ? `已读取 ${records.length} 条${query.trim() ? '匹配记录' : ''}` : ''}</span>
        <button className="ghost-action" type="button" onClick={() => void loadHistory()} disabled={busy}>刷新</button>
        <button className="ghost-action" type="button" onClick={() => navigate('upload')}>返回上传</button>
      </div>
    </section>
    {error && <section className="state-message error" role="alert">{error}</section>}
    {openingSource && <ErrorNotice error={state.error?.stage === 'inspect' ? state.error : null} />}
    <section className="oi-history-layout" aria-busy={busy}>
      <div className="oi-history-list" aria-label="已保存报告列表">
        <div className="oi-history-filter"><label htmlFor="oi-history-search">筛选历史报告</label><input id="oi-history-search" type="search" maxLength={80} disabled={!!deletingId || state.loading.inspect}
          value={query} onChange={(event) => { gate.current.cancel(); setSelected(null); setOpeningSource(false); setQuery(event.target.value); }} placeholder="项目、目标、变更类型…" /></div>
        {records.length ? records.map((record) => <article key={record.id} className={selected?.id === record.id ? 'oi-history-row is-selected' : 'oi-history-row'}>
          <button className="oi-history-open" type="button" aria-pressed={selected?.id === record.id} onClick={() => void openReport(record.id)} disabled={busy}>
            <span><b>{record.project_name}</b><small>{formatTime(record.created_at)}</small></span>
            <code>{record.target_id || '目标未提供'}</code>
            <span>{summaryText(record.summary)} · 覆盖 {statusLabel(record.coverage_status)}</span>
          </button>
          <button className="oi-history-delete" type="button" onClick={() => void deleteHistoryRecord(record)} disabled={busy}>{deletingId === record.id ? '删除中…' : '删除'}</button>
        </article>) : <div className="oi-history-empty" role="status"><b>{busy ? '正在读取历史报告' : error ? '历史报告暂时不可用' : query.trim() ? '没有匹配的历史报告' : '还没有保存过报告'}</b></div>}
        {records.length > 0 && hasMore && <div className="oi-history-more"><button className="ghost-action" type="button" onClick={() => void loadMoreHistory()} disabled={busy}>{status === 'loading-more' ? '加载中…' : '加载更多'}</button></div>}
      </div>
      <div className="oi-history-detail">
        {selected?.report ? <>
          <div className="oi-history-source">
            <span>{snapshot ? '已关联项目快照' : '此报告未关联已保存快照'}</span>
            <div className="oi-history-source-actions">
              <ReportDownload report={selected.report} projectName={selected.project_name} reportId={selected.id} mode="history" disabled={busy} />
              {snapshot && <button className="ghost-action" type="button" onClick={() => void openSourceProject()} disabled={busy}>{state.loading.inspect ? '正在打开…' : '打开来源项目'}</button>}
            </div>
          </div>
          <WithoutProjectSource><ReportResults report={selected.report} mode="history" /></WithoutProjectSource>
        </> : <section className="detail-card empty-state-card"><h2>{busy ? '正在读取历史报告' : '未选择报告'}</h2></section>}
      </div>
    </section>
  </div>;
}
