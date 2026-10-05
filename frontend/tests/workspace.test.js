import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createRequestGate, sourceTree } from '../src/components/workspace/requestGate.js'
import { createApiClient } from '../src/api/client.js'
import { createServer } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { fileURLToPath } from 'node:url'

test('new reading request aborts old transport and rejects a late response', () => {
  const gate = createRequestGate(), old = gate.begin(), current = gate.begin()
  assert.equal(old.controller.signal.aborted, true)
  assert.equal(gate.current(old), false)
  assert.equal(gate.current(current), true)
  gate.cancel()
  assert.equal(current.controller.signal.aborted, true)
  assert.equal(gate.current(current), false)
})

test('source tree preserves nested filenames and prototype-like directory names', () => {
  const files = [{ path: 'src/pkg/main.py' }, { path: '__proto__/constructor.py' }, { path: 'utils.py' }]
  const tree = sourceTree(files)
  assert.deepEqual(tree.directories.src.directories.pkg.files, [files[0]])
  assert.deepEqual(tree.directories.__proto__.files, [files[1]])
  assert.deepEqual(tree.files, [files[2]])
  assert.equal(Object.getPrototypeOf(tree.directories), null)
})

test('source and questions reupload the original File, fingerprint and root without manual boundary', async () => {
  const file = new File(['actual zip'], 'current.zip'), fingerprint = 'a'.repeat(64), requests = []
  const controller = new AbortController()
  const client = createApiClient({ fetchImpl: async (url, options) => {
    requests.push([url, options])
    assert.equal(options.body.get('file'), file)
    assert.equal(options.body.get('expected_fingerprint'), fingerprint)
    assert.equal(options.body.get('analysis_root'), 'src')
    assert.equal(options.signal, controller.signal)
    assert.equal(new Headers(options.headers).has('Content-Type'), false)
    return new Response(JSON.stringify({ success: true }))
  } })
  await client.source(file, fingerprint, { path: 'src/pkg/main.py', analysisRoot: 'src', signal: controller.signal })
  const change = { change_domain: 'module', change_type: 'remove_module', target_module_id: 'utils' }
  await client.question(file, change, fingerprint, { question: '为什么需要检查？', findingIndex: 0, history: [], analysisRoot: 'src', signal: controller.signal })
  assert.equal(requests[0][0], '/api/v1/projects/source')
  assert.equal(requests[0][1].body.get('path'), 'src/pkg/main.py')
  assert.equal(requests[1][0], '/api/v1/reports/questions')
  assert.deepEqual(JSON.parse(requests[1][1].body.get('change')), change)
  assert.equal(requests[1][1].body.get('finding_index'), '0')
  assert.equal(requests[1][1].body.get('history'), '[]')
})

let server, ReportQuestions
before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), configFile: false,
    cacheDir: 'node_modules/.vite-workspace-tests', logLevel: 'silent', server: { middlewareMode: true }, appType: 'custom' })
  ReportQuestions = (await server.ssrLoadModule('/src/components/workspace/ReportQuestions.jsx')).default
})
after(async () => { await server?.close() })

test('partial and demo questions show the real boundaries instead of fabricated answers', () => {
  const html = renderToStaticMarkup(createElement(ReportQuestions, { report: { coverage: { status: 'partial' } } }))
  assert.ok(html.includes('覆盖不完整'))
  assert.ok(html.includes('演示记录不发送真实模型请求'))
  assert.ok(html.includes('继续了解这次变更'))
  assert.ok(html.includes('disabled'))
  assert.ok(!html.includes('模型调用成功'))
})
