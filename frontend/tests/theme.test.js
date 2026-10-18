import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const tokens = readFileSync(new URL('../src/tokens.css', import.meta.url), 'utf8')
const app = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8')
const shell = readFileSync(new URL('../src/components/AppShell.jsx', import.meta.url), 'utf8')

test('themes provide the original purple palette and a technology blue palette', () => {
  assert.match(tokens, /--oi-brand-purple: #7134C6/)
  assert.match(tokens, /:root\[data-theme='blue'\]/)
  assert.match(tokens, /--oi-trace: #55B9FF/)
  assert.match(tokens, /--oi-canvas: #06111D/)
})

test('the app applies and persists the selected theme through the topbar control', () => {
  assert.match(app, /openimpact-theme/)
  assert.match(app, /document\.documentElement\.dataset\.theme = theme/)
  assert.match(shell, /className="oi-theme-toggle"/)
  assert.match(shell, /切换到科技蓝主题/)
  assert.match(shell, /切换到深紫主题/)
})

test('the workbench navigation keeps the planned scope page available', () => {
  assert.match(shell, />功能范围<\/a>/)
  assert.match(app, /PlannedPage/)
})
