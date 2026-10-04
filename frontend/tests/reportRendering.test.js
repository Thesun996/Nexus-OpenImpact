import test, { after, before } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const fixture = JSON.parse(readFileSync(new URL('../src/demo/fixtures/analyze.json', import.meta.url), 'utf8'))
let server
let ReportResults
let ErrorNotice

before(async () => {
  // Reuse the project's Vite JSX transform; no browser/testing dependency or
  // production-only mock hook is needed to verify actual report rendering.
  server = await createServer({
    root: fileURLToPath(new URL('..', import.meta.url)),
    configFile: false,
    cacheDir: 'node_modules/.vite-report-rendering-tests',
    logLevel: 'silent',
    server: { middlewareMode: true },
    appType: 'custom',
  })
  const module = await server.ssrLoadModule('/src/pages/ReportPage.jsx')
  ReportResults = module.ReportResults
  ErrorNotice = (await server.ssrLoadModule('/src/pages/PageParts.jsx')).ErrorNotice
})

after(async () => { await server?.close() })

function render(report, index = 0) {
  return renderToStaticMarkup(createElement(ReportResults, { report, initialSelectedIndex: index }))
}

function clone() { return structuredClone(fixture) }

test('Direct, 1-hop and 2-hop selections render their own source and same-slot explanation', () => {
  fixture.evidences.forEach((evidence, index) => {
    const html = render(fixture, index)
    assert.ok(html.includes(evidence.location.file))
    assert.ok(html.includes(`${evidence.location.file}:${evidence.location.line}:${evidence.location.column}`))
    assert.ok(html.includes(evidence.rule))
    assert.ok(html.includes(fixture.explanations[index].explanation.summary))
    fixture.explanations.forEach((other, otherIndex) => {
      if (otherIndex !== index) assert.ok(!html.includes(other.explanation.summary))
    })
    if (index > 0) {
      assert.ok(html.includes(evidence.propagation_path[0].symbols.join(' → ')))
      assert.ok(html.includes('原始 Direct 引用：'))
      assert.ok(html.includes('调用点 1：'))
    }
  })
})

test('zero-impact report renders actual zero counts without earlier source or explanation', () => {
  const report = clone()
  report.change.target_symbol_id = 'page.page'
  report.change.added_parameter.name = 'zone'
  // The overview now renders both real signatures. Keep this case internally
  // consistent with page() -> page(zone), including its empty before signature.
  report.change.before = { ...report.change.before, name: 'page', parameters: [] }
  report.change.after = { ...report.change.after, name: 'page', parameters: [{ ...report.change.after.parameters[1], name: 'zone' }] }
  report.direct_impacts = []
  report.indirect_impacts = []
  report.evidences = []
  report.explanations = []
  report.summary.direct_impact_count = 0
  report.summary.indirect_1hop_count = 0
  report.summary.indirect_2hop_count = 0
  const html = render(report)
  assert.equal((html.match(/<strong>0<\/strong>/g) || []).length, 5)
  assert.ok(html.includes('当前已解析范围内没有确定 Direct 或 Indirect Impact'))
  assert.ok(!html.includes('utils.format_date'))
  assert.ok(!html.includes('timezone'))
  assert.ok(!html.includes('return format_date'))
  assert.ok(!html.includes(fixture.explanations[0].explanation.summary))
})

test('unavailable Evidence retains findings, call location and diagnostics without borrowing source', () => {
  const report = clone()
  const evidence = report.evidences[0]
  evidence.status = 'unavailable'
  evidence.location = null
  evidence.source_snippet = null
  evidence.source_hash = null
  evidence.diagnostics = [{ code: 'evidence_unavailable', message: '证据生成失败，影响结果仍可查看。' }]
  report.explanations[0] = { evidence: structuredClone(evidence), explanation: null, diagnostics: [{ code: 'evidence_unavailable', message: '源码证据不可用，无法生成解释。' }] }
  const html = render(report)
  assert.ok(html.includes('Evidence unavailable'))
  assert.ok(html.includes('Explanation unavailable'))
  assert.ok(html.includes('证据生成失败，影响结果仍可查看。'))
  assert.ok(html.includes('report.py:5:11'))
  assert.doesNotMatch(html, /<pre class="code-block"[^>]*>/)
  assert.ok(!html.includes(fixture.explanations[1].explanation.summary))
  assert.equal((html.match(/<strong>1<\/strong>/g) || []).length, 3)
})

test('missing or mismatched Explanation degrades while the actual Evidence stays available', () => {
  const report = clone()
  report.explanations[0].explanation = null
  report.explanations[0].diagnostics = [{ code: 'explanation_unavailable', message: '解释生成失败，源码证据仍可查看。' }]
  let html = render(report)
  assert.ok(html.includes('Explanation unavailable'))
  assert.ok(html.includes('解释生成失败，源码证据仍可查看。'))
  assert.match(html, /<pre class="code-block"[^>]*>/)
  report.explanations[0] = structuredClone(report.explanations[1])
  html = render(report)
  assert.ok(html.includes('report_explanation_mismatch'))
  assert.ok(!html.includes(fixture.explanations[1].explanation.summary))
})

test('invalid Explanation fields do not break rendering or become claimed model success', () => {
  const report = clone()
  report.explanations[0].explanation = { summary: { unsafe: true }, confidence: 1 }
  const html = render(report)
  assert.ok(html.includes('Explanation unavailable'))
  assert.ok(html.includes('中文辅助解释'))
  assert.ok(html.includes('请求成功和解释非空均不能证明 DeepSeek 真实调用成功'))
})

test('source snippets and explanation text are escaped ordinary text, including HTML-like code', () => {
  const report = clone()
  const snippet = 'return format_date(date)  # <img src=x onerror="alert(1)">'
  report.evidences[0].source_snippet = snippet
  report.explanations[0].evidence = structuredClone(report.evidences[0])
  report.explanations[0].explanation.why_affected = snippet
  const html = render(report)
  assert.ok(html.includes('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;'))
  assert.ok(!html.includes('<img src=x'))
  assert.ok(!html.includes('dangerouslySetInnerHTML'))
})

test('partial, manual review, unresolved and pre-existing data stay separate from definite Impact', () => {
  const report = clone()
  report.coverage.status = 'partial'
  report.coverage.files_with_parse_errors = 1
  report.manual_reviews = [{
    caller_symbol_id: 'extra.uncertain', target_symbol_id: 'utils.format_date', file: 'extra.py', line: 3, column: 0,
    before_status: 'manual_review', after_status: 'manual_review',
    before_reason: '参数展开无法确定', after_reason: '参数展开无法确定',
    reason: '需要人工检查', rule_id: 'argument_expansion_unknown',
  }]
  report.pre_existing_problems = [{
    caller_symbol_id: 'extra.preexisting', target_symbol_id: 'utils.format_date', file: 'extra.py', line: 7, column: 4,
    before_status: 'incompatible', after_status: 'incompatible', before_reason: '原先缺少 date', after_reason: '仍缺少 date',
  }]
  report.diagnostics.parse_errors = [{ file: 'broken.py', line: 1, column: 0, kind: 'syntax_error', message: '语法错误' }]
  report.diagnostics.unresolved_calls = [{ file: 'extra.py', line: 5, column: 4, expression: 'missing_formatter', reason: 'name_not_indexed' }]
  report.summary.manual_review_count = 1
  report.summary.pre_existing_problem_count = 1
  report.summary.unresolved_call_count = 1
  const html = render(report)
  assert.ok(html.includes('partial：分析范围不完整'))
  assert.ok(html.includes('零条影响也不表示整个项目确定无影响'))
  assert.ok(html.includes('extra.uncertain'))
  assert.ok(html.includes('extra.py:3:0'))
  assert.ok(html.includes('不作为确定间接传播起点'))
  assert.ok(html.includes('修改前已经存在的问题，不归因于本次 Change'))
  assert.ok(html.includes('missing_formatter'))
  assert.ok(html.includes('name_not_indexed'))
  assert.ok(html.includes('broken.py:1:0'))
  assert.ok(!html.includes('missing_formatter →'))
  assert.equal((html.match(/aria-pressed=/g) || []).length, 3)
})

test('summary mismatch is visible and preserves Core counts instead of creating fake findings', () => {
  const report = clone()
  report.summary.direct_impact_count = 7
  const html = render(report)
  assert.ok(html.includes('report_count_mismatch'))
  assert.ok(html.includes('<strong>7</strong>'))
  assert.equal((html.match(/aria-pressed=/g) || []).length, 3)
})

test('multiple Indirect sources use the shortest existing representative for list and unavailable location', () => {
  const report = clone()
  const finding = report.indirect_impacts[0]
  const shorter = structuredClone(finding.sources[0])
  const longer = structuredClone(shorter)
  longer.propagation_path = [
    { caller_symbol_id: 'dashboard.dashboard', callee_symbol_id: 'relay.relay', file: 'dashboard.py', line: 9, column: 2, resolution_basis: 'from_import' },
    { caller_symbol_id: 'relay.relay', callee_symbol_id: 'report.report', file: 'relay.py', line: 4, column: 8, resolution_basis: 'from_import' },
    structuredClone(shorter.propagation_path[1]),
  ]
  finding.sources = [longer, shorter]
  const evidence = report.evidences[1]
  evidence.propagation_path = [
    {
      symbols: ['dashboard.dashboard', 'relay.relay', 'report.report', 'utils.format_date'],
      call_sites: longer.propagation_path.map(({ file, line, column }) => ({ file, line, column, end_line: null })),
      direct_evidence_reference: evidence.evidence_reference,
    },
    structuredClone(evidence.propagation_path[0]),
  ]
  report.explanations[1].evidence = structuredClone(evidence)
  let html = render(report, 1)
  let selectedButton = html.match(/<button[^>]*aria-pressed="true"[^>]*>(.*?)<\/button>/s)?.[1]
  assert.ok(selectedButton.includes('位置：dashboard.py:5:11'))
  assert.ok(!selectedButton.includes('位置：dashboard.py:9:2'))
  assert.ok(html.includes('调用点 1：dashboard.py:9:2'))

  evidence.status = 'unavailable'
  evidence.location = null
  evidence.source_snippet = null
  evidence.source_hash = null
  evidence.propagation_path = []
  evidence.diagnostics = [{ code: 'evidence_unavailable', message: '无法构建源码证据' }]
  report.explanations[1] = { evidence: structuredClone(evidence), explanation: null, diagnostics: [] }
  html = render(report, 1)
  selectedButton = html.match(/<button[^>]*aria-pressed="true"[^>]*>(.*?)<\/button>/s)?.[1]
  assert.ok(selectedButton.includes('位置：dashboard.py:5:11'))
  const sourceCard = html.match(/<article[^>]*aria-label="当前影响的源码证据"[^>]*>(.*?)<\/article>/s)?.[1]
  assert.ok(sourceCard.includes('dashboard.py:5:11'))
  assert.ok(!sourceCard.includes('dashboard.py:9:2'))
  assert.ok(sourceCard.includes('Evidence unavailable'))
})

test('grouping Indirect records preserves the original Evidence and Explanation index', () => {
  const report = clone()
  report.indirect_impacts.reverse()
  report.evidences = [report.evidences[0], report.evidences[2], report.evidences[1]]
  report.explanations = [report.explanations[0], report.explanations[2], report.explanations[1]]
  const html = render(report, 1)
  const selectedButton = html.match(/<button[^>]*aria-pressed="true"[^>]*>(.*?)<\/button>/s)?.[1]
  assert.ok(selectedButton.includes('page.page'))
  assert.ok(html.includes('return dashboard()'))
  assert.ok(html.includes(fixture.explanations[2].explanation.summary))
  assert.ok(!html.includes(fixture.explanations[1].explanation.summary))
  assert.ok(!html.includes('report_evidence_mismatch'))
})

test('Direct trace contains only its confirmed caller, target and actual call site', () => {
  const html = render(fixture)
  const trace = html.match(/<section[^>]*aria-label="当前影响的调用路径"[^>]*>(.*?)<\/section>/s)?.[1]
  assert.ok(trace, 'the selected finding must have a separate Trace view')
  assert.ok(trace.includes('report.report → utils.format_date'))
  assert.ok(trace.includes('report.py:5:11'))
  assert.ok(!trace.includes('dashboard.dashboard'))
  assert.ok(!trace.includes('page.page'))
})

test('missing Indirect path stays unavailable rather than inventing links from names or other findings', () => {
  const report = clone()
  report.evidences[1].status = 'unavailable'
  report.evidences[1].location = null
  report.evidences[1].source_snippet = null
  report.evidences[1].source_hash = null
  report.evidences[1].propagation_path = []
  report.explanations[1] = { evidence: structuredClone(report.evidences[1]), explanation: null, diagnostics: [] }
  const html = render(report, 1)
  const trace = html.match(/<section[^>]*aria-label="当前影响的调用路径"[^>]*>(.*?)<\/section>/s)?.[1]
  assert.ok(trace.includes('Trace unavailable'))
  assert.ok(!trace.includes('dashboard.dashboard → report.report'))
  assert.doesNotMatch(html, /<pre class="code-block"[^>]*>/)
  assert.ok(html.includes('dashboard.py:5:11'))
})

test('conflicting Evidence metadata produces unavailable without displaying another snippet', () => {
  const report = clone()
  report.evidences[0].location.column += 1
  report.explanations[0].evidence = structuredClone(report.evidences[0])
  const html = render(report)
  assert.ok(html.includes('report_evidence_mismatch'))
  assert.ok(html.includes('Evidence unavailable'))
  assert.ok(html.includes('Explanation unavailable'))
  assert.doesNotMatch(html, /<pre class="code-block"[^>]*>/)
  assert.ok(!html.includes(fixture.explanations[0].explanation.summary))
})

test('rendering reports and grouping the index never mutate response arrays or snapshots', () => {
  const report = clone()
  const original = JSON.stringify(report)
  for (const index of [2, 0, 1]) render(report, index)
  assert.equal(JSON.stringify(report), original)
})

test('available source exposes a named keyboard stop without altering the snippet', () => {
  const html = render(fixture)
  assert.match(html, /<pre class="code-block" tabindex="0" aria-label="源码片段，可横向滚动">/)
  assert.ok(html.includes(fixture.evidences[0].source_snippet))
})

test('error notices preserve actual diagnostics without a contradictory empty success message', () => {
  for (const diagnostics of [[], {}]) {
    const html = renderToStaticMarkup(createElement(ErrorNotice, {
      error: { code: 'invalid_zip', message: '上传文件不是有效 ZIP。', diagnostics },
    }))
    assert.ok(html.includes('invalid_zip'))
    assert.ok(html.includes('上传文件不是有效 ZIP。'))
    assert.ok(!html.includes('未发现诊断项'))
  }
  const html = renderToStaticMarkup(createElement(ErrorNotice, {
    error: { code: 'fingerprint_mismatch', message: '项目指纹不一致。', diagnostics: [{ code: 'snapshot_changed', message: '请重新 Inspect。' }] },
  }))
  assert.ok(html.includes('snapshot_changed'))
  assert.ok(html.includes('请重新 Inspect。'))
  assert.ok(html.includes('返回上传页'))
})

test('provider provenance is an optional disclosure while evidence and confidence limits stay visible', () => {
  const html = render(fixture)
  assert.match(html, /<details class="oi-explanation-details"><summary>解释来源说明<\/summary>/)
  assert.ok(html.includes('请求成功和解释非空均不能证明 DeepSeek 真实调用成功'))
  assert.ok(html.includes('中文辅助解释'))
  const explanationBeforeDisclosure = html.split('<details class="oi-explanation-details">')[0]
  assert.ok(explanationBeforeDisclosure.includes('代码运行失败的概率'))
  assert.ok(explanationBeforeDisclosure.includes(fixture.explanations[0].explanation.why_affected))
})
