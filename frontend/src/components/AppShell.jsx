import { useWorkflow } from '../state/WorkflowContext.jsx'

const navigation = [
  { label: '首页', icon: '⌂', page: 'upload' },
  { label: '变更分析', icon: '‹›', page: 'functions' },
  { label: '影响范围', icon: '⌘', page: 'report' },
  { label: '调用关系', icon: '⌬', page: 'planned' },
  { label: '依赖分析', icon: '◇', page: 'planned' },
  { label: '历史记录', icon: '◴', page: 'planned' },
  { label: '配置管理', icon: '⚙', page: 'planned' },
]

export default function AppShell({ page, navigate, children }) {
  const { state, actions } = useWorkflow()
  const isDemo = state.mode === 'demo'
  const projectName = state.inspect?.project_name || '等待上传'
  const healthStatus = state.health?.status || 'idle'
  const healthLabel = healthStatus === 'ok' ? '后端已连接'
    : healthStatus === 'checking' ? '正在检查后端连接'
      : healthStatus === 'error' ? '后端连接检查失败' : '后端连接待检查'

  function startProject() {
    actions.reset()
    navigate('upload')
  }

  function handleNavigation(event, nextPage) {
    event.preventDefault()
    navigate(nextPage)
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">N</div>
          <span>Nexus OpenImpact</span>
        </div>

        <div className="project-switcher">
          <div className="select-button" title={projectName}>
            <span className="line-icon" aria-hidden="true">▣</span>
            <span>{projectName}</span>
          </div>
          <div className="select-button" title={state.file?.name || '尚未选择原始 ZIP'}>
            <span className="line-icon" aria-hidden="true">⑂</span>
            <span>{state.file?.name || (isDemo ? '固定 signature_change 样例' : '本地 ZIP')}</span>
          </div>
        </div>

        <nav className="side-nav" aria-label="主导航">
          {navigation.map((item) => {
            const active = item.page !== 'planned' && (item.page === page || (item.page === 'functions' && page === 'change'))
            return (
              <a
                key={item.label}
                className={active ? 'active' : undefined}
                aria-current={active ? 'page' : undefined}
                href={`#${item.page}`}
                onClick={(event) => handleNavigation(event, item.page)}
              >
                <span aria-hidden="true">{item.icon}</span>
                {item.label}
              </a>
            )
          })}
        </nav>

        <div className="engine-card">
          <div className="engine-title">
            <span aria-hidden="true">◇</span>
            <span>分析引擎</span>
          </div>
          <ul>
            <li>{isDemo ? '演示记录 · 固定样例' : healthLabel}</li>
            {!isDemo && healthStatus === 'ok' && state.health?.version && <li>Backend v{state.health.version}</li>}
            <li>Python · 模块级函数</li>
            <li>新增必填参数</li>
            <li>{isDemo ? '样例结果来自已保存响应' : state.report ? '当前报告来自上传项目' : state.inspect ? '项目已读取，等待变更分析' : '等待上传项目'}</li>
          </ul>
          <small>{isDemo ? '演示未请求真实分析接口' : '通过 Vite /api 代理连接 Backend v1'}</small>
          <button className="ghost-action" type="button" onClick={() => void actions.checkHealth()} disabled={healthStatus === 'checking'}>{healthStatus === 'checking' ? '检查中…' : '检查后端连接'}</button>
        </div>
      </aside>

      <section className="main-shell">
        <header className="topbar">
          <label className="global-search">
            <span aria-hidden="true">⌕</span>
            <input type="search" placeholder="全项目搜索（规划中）" aria-label="全项目搜索（规划中）" disabled />
          </label>
          <div className="top-actions">
            <a className="top-action-link" href="#planned" onClick={(event) => handleNavigation(event, 'planned')}>▤ 文档</a>
            <a className="top-action-link" href="#planned" onClick={(event) => handleNavigation(event, 'planned')}>⚙ 设置</a>
            <span className="user-chip">中文界面</span>
            <button className="ghost-action" type="button" onClick={startProject}>新项目</button>
          </div>
        </header>

        <div className={`mode-banner ${isDemo ? 'demo' : 'project'}`} role="status">
          <strong>{isDemo ? '演示数据 · 固定样例，未请求真实分析接口' : '实际项目 · 上传 ZIP 后调用 Backend v1'}</strong>
          <span>{isDemo ? '演示结果仅对应 signature_change 样例。' : '三步工作流重复提交同一原始 ZIP，Validate 与 Analyze 校验 Inspect 指纹。'}</span>
        </div>
        <main className="content workflow-content">{children}</main>
      </section>
    </div>
  )
}
