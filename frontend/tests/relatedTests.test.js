import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';

let server, RelatedTests;
before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), configFile: false,
    cacheDir: 'node_modules/.vite-related-tests', logLevel: 'silent', server: { middlewareMode: true }, appType: 'custom' });
  RelatedTests = (await server.ssrLoadModule('/src/components/report/RelatedTests.jsx')).default;
});
after(async () => { await server?.close(); });
const render = report => renderToStaticMarkup(createElement(RelatedTests, { report }));
const candidate = () => ({ test_symbol_id: 'tests.test_report.test_report', file: 'tests/test_report.py', line: 2,
  node_id: 'tests/test_report.py::test_report', relationship: 'upstream', reason: '该候选测试位于已确认直接影响的上游路径。',
  paths: [{ direct_evidence_reference: 'call:report.py:3:11', status: 'available', call_sites: [
    { caller_symbol_id: 'tests.test_report.test_report', callee_symbol_id: 'report.report', file: 'tests/test_report.py', line: 3, column: 11, status: 'available', source_snippet: '    return report()', source_hash: 'a'.repeat(64) },
    { caller_symbol_id: 'report.report', callee_symbol_id: 'utils.f', file: 'report.py', line: 3, column: 11, status: 'available', source_snippet: '    return f(1)', source_hash: 'b'.repeat(64) },
  ] }] });
const report = () => ({ coverage: { status: 'complete' }, related_tests: { status: 'available', candidates: [candidate()], limitations: ['未实际运行测试。'] } });

test('related test shows actual test location, real call path and limitations without mutating report', () => {
  const value = report(), snapshot = JSON.stringify(value), html = render(value);
  for (const text of ['tests/test_report.py:2', 'tests.test_report.test_report → report.report → utils.f', 'report.py:3:11', '上游测试，建议检查', '未实际收集或运行测试', '不保证测试会执行到受影响位置或运行失败']) assert.ok(html.includes(text), text);
  assert.equal(JSON.stringify(value), snapshot);
  assert.ok(html.includes('上方辅助解释未使用这份测试列表'));
});
test('zero candidates and legacy report never claim tests are unnecessary', () => {
  const value = report(); value.related_tests.candidates = [];
  assert.ok(render(value).includes('空列表不代表无需回归测试'));
  assert.ok(render({}).includes('当前报告未提供测试定位信息'));
  assert.ok(!render({}).includes('tests.test_report'));
});
test('partial test boundary remains visible as a concise note before expandable limitations', () => {
  const value = report(); value.coverage.status = 'partial';
  const html = render(value);
  assert.match(html, /<p class="oi-provider-note">未列出的测试仍可能需要检查。<\/p>/);
  assert.ok(html.indexOf('未列出的测试仍可能需要检查') < html.indexOf('oi-test-limits'));
  assert.ok(!html.includes('覆盖不完整'));
  assert.ok(!render(report()).includes('未列出的测试仍可能需要检查'));
});
test('unavailable source does not display old code or hide the whole test record', () => {
  const value = report(); value.related_tests.candidates[0].paths[0].call_sites[0].status = 'unavailable';
  const html = render(value);
  assert.ok(html.includes('该位置源码证据不可用'));
  assert.ok(!html.includes('return report()'));
  assert.ok(html.includes('return f(1)'));
  value.related_tests.status = 'unavailable';
  assert.ok(render(value).includes('相关测试定位暂不可用'));
  assert.ok(!render(value).includes('tests.test_report'));
});
test('uploaded source is rendered as escaped text with a keyboard scroll stop', () => {
  const value = report(); value.related_tests.candidates[0].paths[0].call_sites[0].source_snippet = '<script>alert(1)</script>';
  const html = render(value);
  assert.ok(html.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
  assert.ok(!html.includes('<script>'));
  assert.match(html, /<pre tabindex="0" aria-label="测试关联源码，可横向滚动">/);
});
