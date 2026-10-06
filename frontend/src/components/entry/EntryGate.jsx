import { useCallback, useEffect, useRef, useState } from 'react'
import { useReducedMotionPreference } from '../../motion/reducedMotion.js'
import { startBrandReveal } from './brandReveal.js'
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

export function LoginView({ onEnter }) {
  const heading = useRef(null)
  useEffect(() => { heading.current?.focus({ preventScroll: true }) }, [])
  return <main className="oi-entry oi-login" aria-labelledby="oi-login-title">
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
      <form className="oi-login-form" onSubmit={(event) => { event.preventDefault(); onEnter() }}>
        <p className="oi-login-product">代码变更影响分析</p>
        <h1 id="oi-login-title" ref={heading} tabIndex={-1}>进入项目工作台</h1>
        <p className="oi-login-intro">从你的 Python 项目开始。</p>
        <div className="oi-login-demo-note" id="oi-login-demo-note"><span aria-hidden="true" />演示登录，无需填写账号密码。</div>
        <div className="oi-login-fields">
          <label htmlFor="oi-login-account">用户名 <span>选填</span></label>
          <input id="oi-login-account" type="text" placeholder="你的称呼" autoComplete="off" aria-describedby="oi-login-demo-note" />
          <label htmlFor="oi-login-password">密码 <span>选填</span></label>
          <input id="oi-login-password" type="password" placeholder="可留空，请勿填写真实密码" autoComplete="off" aria-describedby="oi-login-demo-note" />
        </div>
        <button className="oi-login-submit primary-action" type="submit">登录</button>
        <p className="oi-login-footnote">点击登录即可进入。本页不验证或保存账号信息。</p>
      </form>
      <p className="oi-login-footer">Nexus OpenImpact<span>让代码变更有据可查</span></p>
    </section>
  </main>
}

export default function EntryGate({ children, onEnter }) {
  const reducedMotion = useReducedMotionPreference()
  const [stage, setStage] = useState('splash')
  const showLogin = useCallback(() => setStage((current) => current === 'splash' ? 'login' : current), [])
  useEffect(() => { if (reducedMotion) showLogin() }, [reducedMotion, showLogin])
  useEffect(() => {
    if (stage === 'workbench') document.getElementById('oi-main')?.focus({ preventScroll: true })
  }, [stage])
  if (stage === 'workbench') return children
  if (stage === 'login' || reducedMotion) return <LoginView onEnter={() => { onEnter(); setStage('workbench') }} />
  return <BrandSplash onComplete={showLogin} />
}
