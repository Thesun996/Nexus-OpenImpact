import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { checkedSuggestions, createRequestGate, sourceTree } from '../src/components/workspace/requestGate.js'
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
  assert.ok(html.includes('生成推荐追问'))
  assert.ok(!html.includes('我应该先检查哪些位置？'))
})

test('recommendations use the same uploaded snapshot without answer history or a fixed question', async () => {
  const file = new File(['actual chosen zip'], 'current.zip'), fingerprint = 'b'.repeat(64)
  const change = { target_symbol_id: 'utils.f', change_type: 'rename_parameter', parameter_name: 'timeout', new_parameter_name: 'delay' }
  const controller = new AbortController()
  const client = createApiClient({ fetchImpl: async (url, options) => {
    assert.equal(url, '/api/v1/reports/question-suggestions')
    assert.equal(options.body.get('file'), file)
    assert.equal(options.body.get('expected_fingerprint'), fingerprint)
    assert.equal(options.body.get('analysis_root'), 'src')
    assert.equal(options.body.get('finding_index'), '2')
    assert.deepEqual(JSON.parse(options.body.get('change')), change)
    assert.equal(options.body.has('question'), false)
    assert.equal(options.body.has('history'), false)
    assert.equal(options.signal, controller.signal)
    assert.equal(new Headers(options.headers).has('Content-Type'), false)
    return new Response(JSON.stringify({ success: true }))
  } })
  await client.questionSuggestions(file, change, fingerprint, { analysisRoot: 'src', findingIndex: 2, signal: controller.signal })
})

test('recommendation response cannot reuse a different snapshot or label fallback as model success', () => {
  const fingerprint = 'a'.repeat(64)
  const result = { project_fingerprint: fingerprint, finding_index: 0, status: 'available', provider: 'deepseek', message: '模型推荐追问',
    questions: [{ question: '当前调用有哪些位置需要检查？', citations: [] }, { question: '这些证据还有哪些边界？', citations: [] }] }
  assert.equal(checkedSuggestions(result, fingerprint, 0), result)
  for (const overrides of [{ project_fingerprint: 'b'.repeat(64) }, { finding_index: 1 }, { provider: 'fallback' },
    { status: 'unavailable' }, { questions: [] }, { questions: [{ question: '问题' }] }]) {
    assert.throws(() => checkedSuggestions({ ...result, ...overrides }, fingerprint, 0))
  }
  assert.equal(checkedSuggestions({ ...result, provider: 'rule', status: 'unavailable', questions: [] }, fingerprint, 0).questions.length, 0)
})
