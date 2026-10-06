import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { startBrandReveal } from '../src/components/entry/brandReveal.js'

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

test('login truthfully offers an optional frontend demo without external authentication', () => {
  const html = renderToStaticMarkup(createElement(LoginView, { onEnter: () => {} }))
  assert.ok(html.includes('演示登录，无需填写账号密码。'))
  assert.ok(html.includes('本页不验证或保存账号信息。'))
  assert.ok(html.includes('请勿填写真实密码'))
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
