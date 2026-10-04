import { useRef } from 'react'
import { useWorkflow } from '../state/WorkflowContext.jsx'
import MovingMarker from '../motion/MovingMarker.jsx'

const navigation = [
  { label: '上传项目', page: 'upload' },
  { label: '选择函数', page: 'functions' },
  { label: '配置变更', page: 'change' },
  { label: '分析报告', page: 'report' },
]

export default function AppShell({ page, navigate, children }) {
  const { state, actions } = useWorkflow()
  const navRef = useRef(null)
  const isDemo = state.mode === 'demo'
  const projectName = state.inspect?.project_name || '尚未读取项目'
  const healthStatus = state.health?.status || 'idle'
  const healthLabel = healthStatus === 'ok' ? '后端已连接'
    : healthStatus === 'checking' ? '正在检查连接'
      : healthStatus === 'error' ? '后端连接失败' : '连接待检查'

  function startProject() {
    actions.reset()
    navigate('upload')
  }

  function handleNavigation(event, nextPage) {
    event.preventDefault()
    navigate(nextPage)
  }

  return (
    <div className="oi-shell">
      <a className="oi-skip-link" href="#oi-main" onClick={(event) => {
        // Focus the content without changing the application's hash route.
        event.preventDefault()
        document.getElementById('oi-main')?.focus()
      }}>跳到当前页面内容</a>
      <aside className="oi-rail" aria-label="工作台导航">
        <a className="oi-rail-brand" href="#upload" onClick={(event) => handleNavigation(event, 'upload')} aria-label="OpenImpact 上传项目">
          <svg viewBox="0 0 32 32" className="oi-brand-mark" aria-hidden="true">
            <path d="M7 7v18M7 16h18M7 7h10" />
            <circle cx="7" cy="7" r="3" /><circle cx="7" cy="25" r="3" /><circle cx="25" cy="16" r="3" />
          </svg>
        </a>
        <nav ref={navRef} className="oi-rail-nav" aria-label="主导航">
          {navigation.map((item, index) => (
            <a key={item.page} className={page === item.page ? 'oi-nav-item is-current' : 'oi-nav-item'}
              aria-current={page === item.page ? 'page' : undefined} href={`#${item.page}`}
              onClick={(event) => handleNavigation(event, item.page)}>
              <span className="oi-nav-number" aria-hidden="true">{index + 1}</span>
              <span>{item.label}</span>
            </a>
          ))}
          <MovingMarker containerRef={navRef} selector=".is-current" identity={page} className="oi-step-marker" />
        </nav>
        <a className="oi-scope-link" href="#planned" onClick={(event) => handleNavigation(event, 'planned')}>功能范围</a>
        <span className="oi-rail-caption" aria-hidden="true">Change<br />Trace<br />Evidence</span>
      </aside>

      <section className="oi-workspace">
        <header className="oi-topbar">
          <div className="oi-wordmark"><strong>OpenImpact</strong><span>Tracework</span></div>
          <div className="oi-project-context">
            <span className="oi-context-label">{state.inspect ? '当前项目' : state.file ? '已选择 ZIP' : '本地工作台'}</span>
            <strong>{projectName}</strong>
            <span className="oi-file-name">{state.file?.name || (isDemo ? '固定 signature_change 样例' : '等待选择原始 ZIP')}</span>
          </div>
          <div className="oi-top-actions">
            <button className={`oi-connection ${healthStatus === 'ok' ? 'is-connected' : healthStatus === 'error' ? 'is-error' : ''}`}
              type="button" onClick={() => void actions.checkHealth()} disabled={healthStatus === 'checking'}
              aria-label={`${healthLabel}，检查后端连接`}>
              <span className="oi-connection-dot" aria-hidden="true" />
              <span>{healthLabel}</span>
              {healthStatus === 'ok' && state.health?.version && <small>v{state.health.version}</small>}
            </button>
            <button className="ghost-action oi-new-project" type="button" onClick={startProject}>新项目</button>
          </div>
        </header>

        <div className={`oi-session-strip ${isDemo ? 'is-demo' : ''}`} role="status">
          <strong>{isDemo ? '演示记录' : '实际项目'}</strong>
          <span>{isDemo ? '固定样例，未请求真实分析接口。' : '原始 ZIP 保留在当前会话，刷新后需要重新选择。'}</span>
          <span className="oi-session-scope">Python / 模块级函数 / 新增必填参数</span>
        </div>
        <main id="oi-main" tabIndex={-1} className="content workflow-content oi-content">{children}</main>
      </section>
    </div>
  )
}
