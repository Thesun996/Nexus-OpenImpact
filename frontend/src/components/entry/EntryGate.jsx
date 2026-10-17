import { useCallback, useEffect, useRef, useState } from 'react'
import { useReducedMotionPreference } from '../../motion/reducedMotion.js'
import { startBrandReveal } from './brandReveal.js'
import { startLoginDissolve } from './loginDissolve.js'
import './entry.css'

export function BrandSplash({ onComplete }) {
  const title = useRef(null)
  useEffect(() => startBrandReveal([...title.current.querySelectorAll('[data-brand-character]')], onComplete), [onComplete])
  return <main className="oi-entry oi-splash" aria-label="Nexus OpenImpact 开场">
    <h1 ref={title} className="oi-splash-title" aria-label="Nexus OpenImpact">
      {['Nexus', 'OpenImpact'].map((word) => <span key={word} className="oi-splash-word" aria-hidden="true">
        {[...word].map((character, index) => <span key={index} data-brand-character>{character}</span>)}
      </span>)}
    </h1>
    <p className="oi-splash-caption">看清一次改动的影响</p>
    <button type="button" className="oi-splash-skip ghost-action" onClick={onComplete}>跳过动画</button>
  </main>
}

export function LoginView({ onEnter, leaving = false, reducedMotion = false, onExited }) {
  const view = useRef(null)
  const heading = useRef(null)
  useEffect(() => { heading.current?.focus({ preventScroll: true }) }, [])
  useEffect(() => {
    if (!leaving) return
    if (reducedMotion) { onExited(); return }
    return startLoginDissolve(view.current, onExited)
  }, [leaving, reducedMotion, onExited])
  return <main ref={view} className={`oi-entry oi-login${leaving ? ' is-leaving' : ''}`} aria-labelledby="oi-login-title">
    <section className="oi-login-story" aria-label="项目介绍">
      <div className="oi-login-story-content">
        <p className="oi-entry-brand"><span className="oi-entry-brand-dot" aria-hidden="true" />Nexus OpenImpact</p>
        <h2>从一次改动，<br />看清影响。</h2>
        <p className="oi-login-description">找到受影响的代码，沿着调用路径，理解每一条源码证据。</p>
        <ol className="oi-login-steps">
          <li><span aria-hidden="true">1</span><div><strong>带入你的项目</strong><small>上传 Python 项目的 ZIP</small></div></li>
          <li><span aria-hidden="true">2</span><div><strong>配置一次变更</strong><small>函数签名、模块或公开符号</small></div></li>
          <li><span aria-hidden="true">3</span><div><strong>追踪影响与证据</strong><small>核对源码，再决定检查重点</small></div></li>
        </ol>
      </div>
    </section>
    <section className="oi-login-form-region">
      <form className="oi-login-form" onSubmit={(event) => { event.preventDefault(); if (!leaving) onEnter() }} aria-busy={leaving}>
        <p className="oi-login-product">代码变更影响分析</p>
        <h1 id="oi-login-title" ref={heading} tabIndex={-1}>进入项目工作台</h1>
        <p className="oi-login-intro">从你的 Python 项目开始。</p>
        <div className="oi-login-fields">
          <label htmlFor="oi-login-account">用户名</label>
          <input id="oi-login-account" type="text" placeholder="请输入用户名" autoComplete="off" />
          <label htmlFor="oi-login-password">密码</label>
          <input id="oi-login-password" type="password" placeholder="请输入密码" autoComplete="off" />
        </div>
        <button className="oi-login-submit primary-action" type="submit" aria-disabled={leaving}>登录</button>
      </form>
      <p className="oi-login-footer">Nexus OpenImpact<span>让代码变更有据可查</span></p>
    </section>
  </main>
}

export default function EntryGate({ children, onEnter }) {
  const reducedMotion = useReducedMotionPreference()
  const [stage, setStage] = useState('splash')
  const entered = useRef(false)
  const enteredWithoutMotion = useRef(false)
  const workbench = useRef(null)
  const showLogin = useCallback(() => setStage((current) => current === 'splash' ? 'login' : current), [])
  const enterWorkbench = useCallback(() => {
    if (entered.current) return
    entered.current = true
    enteredWithoutMotion.current = reducedMotion
    onEnter()
    setStage('workbench')
  }, [onEnter, reducedMotion])
  useEffect(() => { if (reducedMotion) showLogin() }, [reducedMotion, showLogin])
  useEffect(() => {
    if (stage === 'workbench') {
      window.scrollTo({ top: 0, behavior: 'instant' })
      document.getElementById('oi-main')?.focus({ preventScroll: true })
    }
  }, [stage])
  useEffect(() => {
    if (stage === 'workbench' && reducedMotion) workbench.current?.getAnimations().forEach(animation => animation.finish())
  }, [stage, reducedMotion])
  if (stage === 'workbench') return <div ref={workbench} className={`oi-entry-workbench${enteredWithoutMotion.current ? ' is-reduced' : ''}`}>{children}</div>
  if (stage === 'login' || stage === 'leaving' || reducedMotion) return <div className="oi-entry-portal">
    <LoginView leaving={stage === 'leaving'} reducedMotion={reducedMotion} onExited={enterWorkbench}
      onEnter={() => { if (reducedMotion) enterWorkbench(); else setStage('leaving') }} />
  </div>
  return <BrandSplash onComplete={showLogin} />
}
