import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { startBrandReveal } from '../src/components/entry/brandReveal.js'
import { startLoginDissolve } from '../src/components/entry/loginDissolve.js'

let server, EntryGate, BrandSplash, LoginView
before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), configFile: false,
    cacheDir: 'node_modules/.vite-entry-tests', logLevel: 'silent', server: { middlewareMode: true }, appType: 'custom' })
  ;({ default: EntryGate, BrandSplash, LoginView } = await server.ssrLoadModule('/src/components/entry/EntryGate.jsx'))
})
after(async () => { await server?.close() })

test('business children are not mounted before entering the workbench', () => {
  let mounted = 0
  function Workbench() { mounted += 1; return createElement('div', null, 'business') }
  const html = renderToStaticMarkup(createElement(EntryGate, { onEnter: () => {} }, createElement(Workbench)))
  assert.equal(mounted, 0)
  assert.ok(!html.includes('business'))
  assert.ok(html.includes('跳过动画'))
})

test('splash has a single accessible brand and words wrap as words', () => {
  const html = renderToStaticMarkup(createElement(BrandSplash, { onComplete: () => {} }))
  assert.ok(html.includes('aria-label="Nexus OpenImpact"'))
  assert.equal((html.match(/data-brand-character/g) || []).length, 15)
  assert.equal((html.match(/class="oi-splash-word" aria-hidden="true"/g) || []).length, 2)
  assert.match(html, /<button[^>]*type="button"[^>]*>跳过动画<\/button>/)
})

test('login uses conventional field copy and preserves the frontend-only entry behavior', () => {
  const html = renderToStaticMarkup(createElement(LoginView, { onEnter: () => {} }))
  assert.ok(html.includes('placeholder="请输入用户名"'))
  assert.ok(html.includes('placeholder="请输入密码"'))
  assert.doesNotMatch(html, /演示|选填|无需填写|可留空|不验证或保存|请勿填写真实密码/)
  assert.ok(!html.includes('aria-describedby="oi-login-demo-note"'))
  assert.ok(!html.includes('required'))
  assert.ok(!html.includes('action='))
  assert.ok(!html.includes('name="password"'))
  assert.ok(!html.includes('Google') && !html.includes('Github'))
  assert.match(html, /<button[^>]*type="submit"[^>]*>登录<\/button>/)
  assert.ok(html.includes('for="oi-login-account"') && html.includes('for="oi-login-password"'))
})

function fakeAnimation() {
  const steps = [], events = []
  let config
  const timeline = { add(step, offset) { steps.push({ step, offset }); return this },
    play() { events.push('play') }, pause() { events.push('pause') } }
  const animation = { timeline(options) { config = options; return timeline }, stagger: (time) => time,
    remove(targets) { events.push(['remove', targets]) } }
  return { animation, steps, events, finish: () => config.complete(), options: () => config }
}

test('reveal runs one enter/exit timeline and completes once without an infinite loop', () => {
  const fake = fakeAnimation(), characters = [1, 2, 3]
  let completed = 0
  const cancel = startBrandReveal(characters, () => completed++, fake.animation)
  assert.equal(fake.options().loop, false)
  assert.equal(fake.options().autoplay, false)
  assert.equal(fake.steps.length, 2)
  assert.equal(fake.steps[0].step.targets, characters)
  assert.deepEqual(fake.steps[0].step.opacity, [0, 1])
  assert.deepEqual(fake.steps[1].step.opacity, [1, 0])
  assert.equal(fake.steps[1].offset, '+=650')
  assert.deepEqual(fake.events, ['play'])
  fake.finish()
  assert.equal(completed, 1)
  cancel()
})

test('skip, preference change and unmount cancel only this timeline and suppress stale completion', () => {
  const fake = fakeAnimation(), characters = [1, 2, 3]
  let completed = 0
  const cancel = startBrandReveal(characters, () => completed++, fake.animation)
  cancel()
  fake.finish()
  assert.equal(completed, 0)
  assert.deepEqual(fake.events, ['play', 'pause', ['remove', characters]])
})

function fakeDissolve() {
  let frames, options, cancellations = 0
  const exit = { cancel() { cancellations += 1 } }
  return {
    element: { animate(keyframes, timing) { frames = keyframes; options = timing; return exit } },
    style: { getPropertyValue: () => '380ms' },
    finish: () => exit.onfinish(), frames: () => frames, options: () => options, cancellations: () => cancellations,
  }
}

test('login dissolves before completion and ignores repeated finish events', () => {
  const fake = fakeDissolve()
  let completed = 0
  startLoginDissolve(fake.element, () => completed++, fake.style)
  assert.equal(completed, 0)
  assert.equal(fake.options().duration, 380)
  assert.equal(fake.options().fill, 'forwards')
  assert.equal(fake.frames()[0].opacity, 1)
  assert.equal(fake.frames().at(-1).opacity, 0)
  fake.finish()
  fake.finish()
  assert.equal(completed, 1)
})

test('cancelled login exit cannot enter a stale workbench', () => {
  const fake = fakeDissolve()
  let completed = 0
  const cancel = startLoginDissolve(fake.element, () => completed++, fake.style)
  cancel()
  fake.finish()
  assert.equal(fake.cancellations(), 1)
  assert.equal(completed, 0)
})

test('outgoing login keeps its submit control focusable while preventing duplicate submissions', () => {
  const html = renderToStaticMarkup(createElement(LoginView, { leaving: true, onEnter: () => {}, onExited: () => {} }))
  assert.ok(html.includes('aria-busy="true"'))
  assert.match(html, /<button[^>]*aria-disabled="true"[^>]*>登录<\/button>/)
  assert.ok(!html.includes(' disabled=""'))
})
