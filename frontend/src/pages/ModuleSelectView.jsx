import { reasonLabel } from '../presentation/labels.js';
import { moduleDiagnosticEntries } from './moduleReportData.js';
import { getSelectedModule } from '../state/workflow.js';
import { CoverageNotice, DiagnosticsList, EmptyWorkflow, ErrorNotice } from './PageParts.jsx';
import DomainSelector from '../components/workflow/DomainSelector.jsx';
import { WorkflowNotes } from '../components/workflow/WorkflowParts.jsx';

export const MODULE_REASONS = {
  unsupported_module_layout: '首版只支持项目根目录的普通 .py 文件；包与嵌套模块暂不支持。',
  module_parse_failed: '源码解析失败，请先查看诊断。', module_source_unavailable: '源码文件无法读取，不能校验快照。', ambiguous_module: '存在同名或大小写歧义，不能确定目标。',
  standard_library_name_collision: '模块名与 Python 标准库冲突，暂不作确定性分析。',
  special_module_unsupported: '特殊入口、包初始化或保留名称暂不支持。',
  invalid_module_name: '不能形成合法的普通 Python 模块名。', non_normalized_module_name: '模块名需要规范化，当前无法安全匹配。',
};

export default function ModuleSelectView({ state, query, onQueryChange, onSelect, onSelectDomain, onReset, navigate }) {
  const inspect = state.inspect;
  const selected = getSelectedModule(state);
  const modules = inspect?.module_inventory?.modules || [];
  const visible = modules.filter(m => `${m.module_id} ${m.file}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="oi-workflow-page oi-functions-page">
    <section className="page-heading"><div><h1>选择分析模块</h1><p>确认真实相对路径与可支持范围，再拟定模块变化。</p></div><button className="ghost-action" onClick={onReset}>重新开始</button></section>
    <WorkflowNotes current={2} mode={state.mode} /><ErrorNotice error={state.error} />
    <DomainSelector domain="module" mode={state.mode} onSelect={onSelectDomain} />
    {!inspect ? <EmptyWorkflow title="尚未读取项目" message="请先上传原始 ZIP 并读取项目。" navigate={navigate} /> : <>
      <CoverageNotice coverage={inspect.module_coverage} />
      <div className="oi-symbol-workspace"><section className="oi-symbol-index" aria-label="模块列表">
        <header><h2>Python 模块候选</h2><span>{visible.length} / {modules.length} 条</span></header>
        <label className="oi-symbol-search"><span>搜索模块或文件</span><input type="search" value={query} onChange={e => onQueryChange(e.target.value)} /></label>
        <div className="oi-symbol-rows">{visible.map(m => <button type="button" className={`oi-symbol-row${selected?.module_id === m.module_id ? ' is-selected' : ''}`} key={m.file}
          disabled={!m.selectable} aria-pressed={selected?.module_id === m.module_id} onClick={() => onSelect(m.module_id)}>
          <span className="oi-symbol-location">{m.file}</span><b>{m.module_id}</b><span>{m.selectable ? '根目录普通模块 · 可分析' : `不支持：${MODULE_REASONS[m.reason] || reasonLabel(m.reason)}`}</span>
          <span className="oi-symbol-selection">{selected?.module_id === m.module_id ? '已选择' : m.selectable ? '选择此模块' : '不可选择'}</span>
        </button>)}{!visible.length && <p className="oi-symbol-empty">当前没有匹配的模块候选，请查看诊断或返回上传。</p>}</div>
        <footer className="oi-symbol-actions"><span>{selected ? `已选择 ${selected.module_id}` : '请选择一个受支持模块'}</span><button type="button" className="primary-action" disabled={!selected || Object.values(state.loading).some(Boolean)} onClick={() => navigate('change')}>配置变更</button></footer>
      </section><aside className="oi-symbol-preview"><h2>当前选择</h2>{selected ? <><b>{selected.module_id}</b><p><code>{selected.file}</code></p><p>仅分析拟定变更。上传的 ZIP 与源码保持原样。</p></> : <p>普通根模块可选择；不支持的候选保留原因说明。</p>}</aside></div>
      <details className="oi-review-section"><summary>模块解析边界与诊断</summary><DiagnosticsList diagnostics={moduleDiagnosticEntries(inspect.module_diagnostics)} /></details>
    </>}
  </div>;
}
