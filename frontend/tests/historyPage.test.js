import test, { after, before } from 'node:test'
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

let server, matchesHistoryQuery, mergeHistoryRecords, summaryText

before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), configFile: false,
    cacheDir: 'node_modules/.vite-history-page-tests', logLevel: 'silent', server: { middlewareMode: true }, appType: 'custom' })
  ;({ matchesHistoryQuery, mergeHistoryRecords, summaryText } = await server.ssrLoadModule('/src/pages/HistoryPage.jsx'))
})

after(async () => { await server?.close() })

test('history summary combines function 1-hop and 2-hop counts without mutating summary', () => {
  const summary = { direct_impact_count: 1, indirect_1hop_count: 2, indirect_2hop_count: 3, manual_review_count: 4 }
  const snapshot = JSON.stringify(summary)
  assert.equal(summaryText(summary), '直接 1 · 间接 5 · 人工检查 4')
  assert.equal(JSON.stringify(summary), snapshot)
})

test('history summary supports module and symbol aggregate fields', () => {
  assert.equal(summaryText({ import_impact_count: 2, module_indirect_impact_count: 1, manual_review_required_count: 3 }), '直接 2 · 间接 1 · 人工检查 3')
  assert.equal(summaryText({ direct_reference_count: 4, symbol_indirect_impact_count: 5 }), '直接 4 · 间接 5 · 人工检查 0')
})

test('history filter searches stable report metadata only', () => {
  const record = { project_name: 'signature_change', source_filename: 'signature_change.zip', target_id: 'utils.format_date',
    change_domain: 'function', change_type: 'add_required_parameter', coverage_status: 'complete' }
  for (const query of ['signature', 'FORMAT_DATE', 'required', 'function', 'complete', 'zip', '']) {
    assert.equal(matchesHistoryQuery(record, query), true, query)
  }
  assert.equal(matchesHistoryQuery(record, 'dashboard'), false)
})

test('history pagination merge keeps existing order and removes duplicate records', () => {
  const current = [{ id: 'a' }, { id: 'b' }]
  const incoming = [{ id: 'b' }, { id: 'c' }]
  assert.deepEqual(mergeHistoryRecords(current, incoming), [{ id: 'a' }, { id: 'b' }, { id: 'c' }])
  assert.deepEqual(current, [{ id: 'a' }, { id: 'b' }])
  assert.deepEqual(incoming, [{ id: 'b' }, { id: 'c' }])
})
