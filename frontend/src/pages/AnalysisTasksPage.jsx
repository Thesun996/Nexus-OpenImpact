import { useEffect, useRef, useState } from 'react';
import { apiClient } from '../api/client.js';
import { createRequestGate } from '../components/workspace/requestGate.js';
import { formatTime } from './HistoryPage.jsx';
import { checkedTask, waitForAnalysisTask } from '../state/analysisTask.js';
import { WithoutProjectSource } from '../components/workspace/SourceWorkspace.jsx';
import { ReportResults } from './ReportPage.jsx';
import ReportDownload from '../components/report/ReportDownload.jsx';
import { CHANGE_TYPES } from '../state/changeDraft.js';
import { MODULE_CHANGE_TYPES } from '../state/moduleDraft.js';
import { SYMBOL_CHANGE_TYPES } from '../state/symbolDraft.js';

const TASK_PAGE_SIZE = 20;

const statusText = {
  queued: '排队中',
  running: '分析中',
  succeeded: '已完成',
  failed: '失败',
};

export function taskStatusLabel(status) {
  return Object.hasOwn(statusText, status) ? statusText[status] : '未知状态';
}

export function taskTargetLabel(change) {
  return change?.target_symbol_id || change?.target_module_id || change?.target_id || change?.target_module || change?.target_symbol || '目标未记录';
}

export function taskChangeLabel(change) {
  const type = change?.operation?.change_type || change?.change_type || (change?.added_parameter ? 'add_required_parameter' : null);
  const label = [...CHANGE_TYPES, ...MODULE_CHANGE_TYPES, ...SYMBOL_CHANGE_TYPES].find(item => item.value === type)?.label || '变更类型未知';
  const parameter = change?.operation?.parameter_name || change?.added_parameter?.name || change?.parameter_name;
  return parameter ? `${label} · ${parameter}` : label;
}

function mergeTasks(current, incoming) {
  const seen = new Set();
  return [...current, ...incoming].filter(item => !seen.has(item.id) && seen.add(item.id));
}

function TaskDetail({ task }) {
  if (!task) return <section className="oi-project-detail" role="status"><h2>未选择任务</h2></section>;
  return <section className="oi-project-detail oi-task-detail">
    <div className="oi-task-detail-heading">
      <h2>{taskStatusLabel(task.status)}</h2>
      <span className={`oi-task-status is-${task.status || 'unknown'}`}>{taskStatusLabel(task.status)}</span>
    </div>
    <dl className="oi-project-facts">
      <div><dt>任务 ID</dt><dd><code>{task.id}</code></dd></div>
      <div><dt>项目快照</dt><dd><code>{task.project_snapshot_id || '未记录'}</code></dd></div>
      <div><dt>目标</dt><dd>{taskTargetLabel(task.change)}</dd></div>
      <div><dt>变更</dt><dd>{taskChangeLabel(task.change)}</dd></div>
      <div><dt>创建时间</dt><dd>{formatTime(task.created_at)}</dd></div>
      <div><dt>更新时间</dt><dd>{formatTime(task.updated_at)}</dd></div>
    </dl>
    {task.status === 'failed' && <section className="state-message error" role="alert"><b>分析未完成</b><p>{task.error_message || '任务失败，请检查快照和变更配置。'}</p></section>}
  </section>;
}

export default function AnalysisTasksPage({ navigate }) {
  const [tasks, setTasks] = useState([]);
  const [selected, setSelected] = useState(null);
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [result, setResult] = useState(null);
  const [readingReport, setReadingReport] = useState(false);
  const gate = useRef(createRequestGate());
  const offset = useRef(0);
  const busy = status.startsWith('loading');

  async function readTask(id, request) {
    const signal = request.controller.signal;
    const task = await apiClient.getAnalysisTask(id, { signal });
    if (!gate.current.current(request)) return;
    checkedTask(task, { id });
    setSelected(task); setStatus('ready');
    if (task.status === 'failed') return;
    try {
      const record = await waitForAnalysisTask(apiClient, task, { signal, onUpdate: updated => {
        if (!gate.current.current(request)) return;
        setSelected(updated); setReadingReport(updated.status === 'succeeded');
        setTasks(current => current.map(item => item.id === updated.id ? updated : item));
      } });
      if (gate.current.current(request)) setResult(record);
    } finally { if (gate.current.current(request)) setReadingReport(false); }
  }

  async function loadTasks(append = false, preferredId = selected?.id) {
    const request = gate.current.begin();
    setStatus(append ? 'loading-more' : 'loading'); setError(null);
    setResult(null); setSelected(null); setReadingReport(false);
    if (!append) { setTasks([]); setHasMore(false); offset.current = 0; }
    try {
      const payload = await apiClient.listAnalysisTasks({ signal: request.controller.signal, limit: TASK_PAGE_SIZE, offset: append ? offset.current : 0 });
      if (!gate.current.current(request)) return;
      if (!Array.isArray(payload.items)) throw new Error('任务列表响应不完整，请重新读取。');
      const items = payload.items;
      items.forEach(item => checkedTask(item));
      offset.current = (append ? offset.current : 0) + items.length;
      setTasks(current => append ? mergeTasks(current, items) : items);
      setHasMore(payload.has_more === true);
      const nextSelected = append ? preferredId : items.some(item => item.id === preferredId) ? preferredId : items[0]?.id;
      if (nextSelected) await readTask(nextSelected, request);
      if (gate.current.current(request)) setStatus('ready');
    } catch (failure) {
      if (gate.current.current(request) && failure.name !== 'AbortError') {
        setError(failure.message || '无法读取分析任务。'); setStatus('error');
      }
    }
  }

  async function openTask(id) {
    const request = gate.current.begin();
    setStatus('loading-detail'); setError(null); setSelected(null); setResult(null); setReadingReport(false);
    try { await readTask(id, request); if (gate.current.current(request)) setStatus('ready'); }
    catch (failure) {
      if (gate.current.current(request) && failure.name !== 'AbortError') {
        setError(failure.message || '无法读取该任务。'); setStatus('error');
      }
    }
  }

  useEffect(() => {
    void loadTasks(false, null);
    return () => gate.current.cancel();
  }, []);

  return <div className="oi-history-page oi-task-page">
    <section className="page-heading">
      <div><h1>分析任务</h1><p>查看分析进度与已保存的结果</p></div>
      <div className="heading-actions">
        <span>{tasks.length ? `已读取 ${tasks.length} 个任务` : ''}</span>
        <button className="ghost-action" type="button" onClick={() => void loadTasks()} disabled={busy}>刷新</button>
        <button className="ghost-action" type="button" onClick={() => navigate('projects')}>项目库</button>
      </div>
    </section>
    {error && <section className="state-message error" role="alert">{error}</section>}
    <section className="oi-history-layout" aria-busy={busy}>
      <div className="oi-history-list" aria-label="分析任务列表">
        {tasks.length ? tasks.map((task) => <article key={task.id} className={selected?.id === task.id ? 'oi-history-row is-selected' : 'oi-history-row'}>
          <button className="oi-history-open" type="button" aria-pressed={selected?.id === task.id} onClick={() => void openTask(task.id)} disabled={busy}>
            <span><b>{taskTargetLabel(task.change)}</b><small>{formatTime(task.updated_at)}</small></span>
            <code>{taskChangeLabel(task.change)}</code>
            <span><span className={`oi-task-status is-${task.status || 'unknown'}`}>{taskStatusLabel(task.status)}</span>{task.result_report_id ? ` · 报告 ${task.result_report_id.slice(0, 8)}` : ''}</span>
          </button>
        </article>) : <div className="oi-history-empty" role="status"><b>{busy ? '正在读取分析任务' : error ? '分析任务暂时不可用' : '还没有分析任务'}</b></div>}
        {tasks.length > 0 && hasMore && <div className="oi-history-more"><button className="ghost-action" type="button" onClick={() => void loadTasks(true)} disabled={busy}>{status === 'loading-more' ? '加载中…' : '加载更多'}</button></div>}
      </div>
      <div className="oi-history-detail"><TaskDetail task={selected} />
        {readingReport && <p role="status">正在读取报告…</p>}
        {result && <>
          <div className="oi-history-source"><b>分析报告 · 已保存</b><ReportDownload report={result.report} projectName={result.project_name} reportId={result.id} mode="history" /></div>
          <WithoutProjectSource><ReportResults report={result.report} mode="history" /></WithoutProjectSource>
        </>}
      </div>
    </section>
  </div>;
}
