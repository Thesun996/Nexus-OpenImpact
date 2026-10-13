import test from 'node:test'
import assert from 'node:assert/strict'
import { ApiError, createApiClient, toWorkflowError } from '../src/api/client.js'

const zip = new File(['the actual selected project ZIP'], 'selected-project.zip', { type: 'application/zip' })
const change = { target_symbol_id: 'page.page', added_parameter: { name: 'zone', kind: 'keyword_only' } }
const fingerprint = 'a'.repeat(64)
const jsonResponse = (payload, status = 200) => new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })

test('health uses the relative Vite API path and returns the complete JSON', async () => {
  const expected = { status: 'ok', version: '0.1.0' }
  const controller = new AbortController()
  const client = createApiClient({ fetchImpl: async (url, options) => {
    assert.equal(url, '/api/v1/health')
    assert.equal(options.method, 'GET')
    assert.equal(options.body, undefined)
    assert.equal(options.signal, controller.signal)
    return jsonResponse(expected)
  } })
  assert.deepEqual(await client.health({ signal: controller.signal }), expected)
})

test('inspect, validate, and analyze each reupload the same original File and content', async () => {
  const seen = []
  const client = createApiClient({ fetchImpl: async (url, options) => {
    assert.equal(options.method, 'POST')
    assert.ok(options.body instanceof FormData)
    assert.equal(new Headers(options.headers).has('Content-Type'), false)
    assert.equal(options.body.get('file'), zip)
    assert.equal(await options.body.get('file').text(), await zip.text())
    seen.push({ url, form: options.body })
    return jsonResponse({ actual: url, symbols: [], summary: { direct_impact_count: 0 } })
  } })
  await client.inspect(zip)
  await client.validate(zip, change, fingerprint)
  const report = await client.analyze(zip, change, fingerprint)
  assert.deepEqual(seen.map(({ url }) => url), ['/api/v1/projects/inspect', '/api/v1/changes/validate', '/api/v1/projects/analyze'])
  assert.deepEqual([...seen[0].form.keys()], ['file'])
  for (const { form } of seen.slice(1)) {
    assert.deepEqual([...form.keys()], ['file', 'change', 'expected_fingerprint'])
    assert.deepEqual(JSON.parse(form.get('change')), change)
    assert.equal(form.get('expected_fingerprint'), fingerprint)
  }
  assert.equal(report.summary.direct_impact_count, 0)
})

test('optional fingerprint is omitted rather than replaced by a demo fingerprint', async () => {
  const client = createApiClient({ fetchImpl: async (_url, options) => {
    assert.equal(options.body.has('expected_fingerprint'), false)
    return jsonResponse({ validation: { valid: true } })
  } })
  await client.validate(zip, change)
  await client.analyze(zip, change, '')
})

test('report history API saves, lists, reads, and deletes persisted reports', async () => {
  const seen = []
  const client = createApiClient({ fetchImpl: async (url, options) => {
    seen.push({ url, options })
    if (url === '/api/v1/reports' && options.method === 'POST') {
      assert.ok(options.body instanceof FormData)
      assert.equal(options.body.get('file'), zip)
      assert.deepEqual(JSON.parse(options.body.get('change')), change)
      assert.equal(options.body.get('expected_fingerprint'), fingerprint)
      return jsonResponse({ record: { id: 'abc123', project_name: 'signature_change' }, report: { summary: {} } })
    }
    if (url === '/api/v1/reports?limit=5&offset=2' && options.method === 'GET') {
      assert.equal(options.body, undefined)
      return jsonResponse({ items: [{ id: 'abc123' }], limit: 5, offset: 2, has_more: false })
    }
    if (url === '/api/v1/reports?limit=5&offset=2&q=format_date' && options.method === 'GET') {
      assert.equal(options.body, undefined)
      return jsonResponse({ items: [{ id: 'abc123' }], limit: 5, offset: 2, query: 'format_date', has_more: true })
    }
    if (url === '/api/v1/reports/report%2Fid' && options.method === 'GET') {
      assert.equal(options.body, undefined)
      return jsonResponse({ id: 'report/id', report: { summary: {} } })
    }
    if (url === '/api/v1/reports/report%2Fid' && options.method === 'DELETE') {
      assert.equal(options.body, undefined)
      return jsonResponse({ deleted: true, id: 'report/id' })
    }
    return jsonResponse({ error: { code: 'unexpected_path', message: url } }, 500)
  } })
  assert.equal((await client.saveReport(zip, change, fingerprint)).record.id, 'abc123')
  assert.equal((await client.listReports({ limit: 5, offset: 2 })).items[0].id, 'abc123')
  const filtered = await client.listReports({ limit: 5, offset: 2, query: ' format_date ' })
  assert.equal(filtered.query, 'format_date')
  assert.equal(filtered.has_more, true)
  assert.equal((await client.getReport('report/id')).id, 'report/id')
  assert.equal((await client.deleteReport('report/id')).deleted, true)
  assert.deepEqual(seen.map(({ url }) => url), ['/api/v1/reports', '/api/v1/reports?limit=5&offset=2', '/api/v1/reports?limit=5&offset=2&q=format_date', '/api/v1/reports/report%2Fid', '/api/v1/reports/report%2Fid'])
})

test('every project operation forwards cancellation without retrying', async () => {
  const controller = new AbortController()
  let calls = 0
  const client = createApiClient({ fetchImpl: async (_url, options) => {
    calls += 1
    assert.equal(options.signal, controller.signal)
    return jsonResponse({ ok: true })
  } })
  await client.inspect(zip, { signal: controller.signal })
  await client.validate(zip, change, fingerprint, { signal: controller.signal })
  await client.analyze(zip, change, fingerprint, { signal: controller.signal })
  assert.equal(calls, 3)
})

test('409 fingerprint mismatch preserves the backend error for a clear UI failure', async () => {
  const payload = { error: { code: 'fingerprint_mismatch', message: '项目指纹与当前上传文件不一致。' } }
  const client = createApiClient({ fetchImpl: async () => jsonResponse(payload, 409) })
  await assert.rejects(client.analyze(zip, change, fingerprint), (error) => {
    assert.ok(error instanceof ApiError)
    assert.equal(error.status, 409)
    assert.equal(error.code, 'fingerprint_mismatch')
    assert.deepEqual(error.payload, payload)
    assert.deepEqual(toWorkflowError(error, 'analyze'), { stage: 'analyze', status: 409, code: 'fingerprint_mismatch', message: payload.error.message, diagnostics: [] })
    return true
  })
})

test('safe JSON 500 is surfaced and does not turn into a mock successful result', async () => {
  let calls = 0
  const payload = { error: { code: 'analysis_failed', message: '项目分析失败，请稍后重试。' } }
  const client = createApiClient({ fetchImpl: async () => { calls += 1; return jsonResponse(payload, 500) } })
  await assert.rejects(client.analyze(zip, change, fingerprint), (error) => error.status === 500 && error.code === 'analysis_failed' && error.message === payload.error.message)
  assert.equal(calls, 1)
})

test('422 Core validation diagnostics and the full validation result remain available', async () => {
  const payload = { change_spec: null, validation: { valid: false, diagnostics: [{ code: 'duplicate_parameter_name', message: '新增参数名与已有参数重名。' }] }, diagnostics: { parse_errors: [] } }
  const client = createApiClient({ fetchImpl: async () => jsonResponse(payload, 422) })
  await assert.rejects(client.validate(zip, change, fingerprint), (error) => {
    assert.equal(error.code, 'duplicate_parameter_name')
    assert.equal(error.status, 422)
    assert.deepEqual(error.diagnostics, payload.validation.diagnostics)
    assert.deepEqual(error.payload.validation, payload.validation)
    return true
  })
})

test('FastAPI detail arrays display field diagnostics without echoing input or context', async () => {
  const client = createApiClient({ fetchImpl: async () => jsonResponse({ detail: [{ type: 'missing', loc: ['body', 'file'], msg: 'Field required', input: 'sensitive input', ctx: { error: 'internal context' } }] }, 422) })
  await assert.rejects(client.inspect(zip), (error) => {
    assert.equal(error.code, 'invalid_request')
    assert.deepEqual(error.diagnostics, [{ code: 'missing', field: 'body.file', message: 'Field required' }])
    assert.equal(JSON.stringify(toWorkflowError(error, 'inspect')).includes('sensitive input'), false)
    assert.equal(JSON.stringify(toWorkflowError(error, 'inspect')).includes('internal context'), false)
    return true
  })
})

test('unreachable backend gives a safe local message without leaking the thrown error', async () => {
  let calls = 0
  const client = createApiClient({ fetchImpl: async () => { calls += 1; throw new Error('private stack and internal location') } })
  await assert.rejects(client.inspect(zip), (error) => error instanceof ApiError && error.code === 'backend_unreachable' && !error.message.includes('private'))
  assert.equal(calls, 1)
  assert.equal(toWorkflowError(new Error('internal stack'), 'health').message.includes('internal'), false)
})

test('AbortError is preserved so cancelled stale requests can be ignored by React state', async () => {
  const aborted = new DOMException('Aborted', 'AbortError')
  const client = createApiClient({ fetchImpl: async () => { throw aborted } })
  await assert.rejects(client.inspect(zip), (error) => error === aborted)
  const bodyClient = createApiClient({ fetchImpl: async () => ({ status: 200, ok: true, json: async () => { throw aborted } }) })
  await assert.rejects(bodyClient.health(), (error) => error === aborted)
})

test('non-JSON responses are never displayed as raw HTML or server traces', async () => {
  const client = createApiClient({ fetchImpl: async () => new Response('<html>private traceback at server path</html>', { status: 500, headers: { 'Content-Type': 'text/html' } }) })
  await assert.rejects(client.analyze(zip, change, fingerprint), (error) => error.code === 'invalid_response' && error.status === 500 && !error.message.includes('private') && error.payload === null)
})

test('invalid JSON objects and unexpected 500 detail use a safe contract error', async () => {
  const arrayClient = createApiClient({ fetchImpl: async () => jsonResponse([]) })
  await assert.rejects(arrayClient.inspect(zip), (error) => error.code === 'invalid_response')
  const unsafeClient = createApiClient({ fetchImpl: async () => jsonResponse({ detail: 'private traceback' }, 500) })
  await assert.rejects(unsafeClient.health(), (error) => error.code === 'server_error' && !error.message.includes('traceback'))
})
