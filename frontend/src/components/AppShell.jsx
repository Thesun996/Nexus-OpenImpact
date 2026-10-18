import { useRef } from 'react'
import { useWorkflow } from '../state/WorkflowContext.jsx'
import MovingMarker from '../motion/MovingMarker.jsx'
import SourceWorkspace from './workspace/SourceWorkspace.jsx'

const navigation = [
  { label: '上传项目', page: 'upload' },
  { label: '选择函数', page: 'functions' },
  { label: '配置变更', page: 'change' },
  { label: '分析报告', page: 'report' },
]

export default function AppShell({ page, navigate, children, theme = 'purple', onThemeChange = () => {} }) {
  const { state, actions } = useWorkflow()
  const navRef = useRef(null)
  const isDemo = state.mode === 'demo'
  const projectName = state.inspect?.project_name || '尚未读取项目'
  const fileName = state.file?.name || state.snapshot?.source_filename || (isDemo ? '固定 signature_change 样例' : '等待选择原始 ZIP')

  function startProject() {
    actions.reset()
    navigate('upload')
  }

  function handleNavigation(event, nextPage) {
    event.preventDefault()
    navigate(nextPage)
  }

  return (
    <SourceWorkspace><div className="oi-shell">
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
              <span>{item.page === 'functions' && state.changeDomain === 'symbol' ? '选择符号' : item.page === 'functions' && state.changeDomain === 'module' ? '选择模块' : item.label}</span>
            </a>
          ))}
          <MovingMarker containerRef={navRef} selector=".is-current" identity={page} className="oi-step-marker" />
        </nav>
        <div className="oi-rail-secondary">
          <a className={page === 'projects' ? 'oi-scope-link is-current' : 'oi-scope-link'} href="#projects" onClick={(event) => handleNavigation(event, 'projects')}>项目库</a>
          <a className={page === 'tasks' ? 'oi-scope-link is-current' : 'oi-scope-link'} href="#tasks" onClick={(event) => handleNavigation(event, 'tasks')}>分析任务</a>
          <a className={page === 'history' ? 'oi-scope-link is-current' : 'oi-scope-link'} href="#history" onClick={(event) => handleNavigation(event, 'history')}>历史报告</a>
        </div>
        <span className="oi-rail-caption" aria-hidden="true">Change<br />Trace<br />Evidence</span>
      </aside>

      <section className="oi-workspace">
        <header className="oi-topbar">
          <div className="oi-wordmark"><strong>OpenImpact</strong><span>Tracework</span></div>
          <div className="oi-project-context">
            <span className="oi-context-label">{state.inspect ? '当前项目' : state.file ? '已选择 ZIP' : '本地工作台'}</span>
            <strong>{projectName}</strong>
            <span className="oi-file-name" title={fileName}>{fileName}</span>
          </div>
          <div className="oi-top-actions">
            <button className="oi-theme-toggle" type="button" onClick={() => onThemeChange(theme === 'blue' ? 'purple' : 'blue')}
              aria-pressed={theme === 'blue'} aria-label={theme === 'blue' ? '切换到深紫主题' : '切换到科技蓝主题'}>
              <span className="oi-theme-swatch" aria-hidden="true" />
              <span>{theme === 'blue' ? '科技蓝' : '深紫'}</span>
            </button>
            <button className="ghost-action oi-new-project" type="button" onClick={startProject}>新项目</button>
          </div>
        </header>

        <div className={`oi-session-strip ${isDemo ? 'is-demo' : ''}`} role="status">
          <strong>{isDemo ? '演示记录' : '实际项目'}</strong>
          <span>{isDemo ? '固定样例，未请求真实分析接口。' : state.snapshot ? '使用项目库已保存快照。' : '原始 ZIP 保留在当前会话，刷新后需要重新选择。'}</span>
          <span className="oi-session-scope">{state.changeDomain === 'symbol' ? 'Python / 公开变量与常量 / 静态引用' : state.changeDomain === 'module' ? 'Python / 根模块 / 静态导入变更' : 'Python / 模块级函数 / 四种签名变更'}</span>
        </div>
        <main id="oi-main" tabIndex={-1} className="content workflow-content oi-content">{children}</main>
      </section>
    </div></SourceWorkspace>
  )
}
