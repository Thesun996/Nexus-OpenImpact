import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';

let server, CoverageNotice;
before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), configFile: false,
    cacheDir: 'node_modules/.vite-coverage', logLevel: 'silent', server: { middlewareMode: true }, appType: 'custom' });
  CoverageNotice = (await server.ssrLoadModule('/src/pages/PageParts.jsx')).CoverageNotice;
});
after(async () => { await server?.close(); });
const render = coverage => renderToStaticMarkup(createElement(CoverageNotice, { coverage }));

test('partial report separates source parsing from call resolution without claiming complete coverage', () => {
  const coverage = { status: 'partial', details: { parsed_python_files: 65, python_files: 65,
    resolved_call_count: 478, unresolved_call_count: 5754, excluded_call_count: 63 } };
  const original = JSON.stringify(coverage), html = render(coverage);
  for (const text of ['分析范围不完整', '65 / 65', '已确认 478 处', '尚未确认 5754 处',
    '63 个调用', '数量不等于本次变更的漏检数', '源码解析成功不代表所有调用关系均已确认']) assert.ok(html.includes(text), text);
  assert.equal(JSON.stringify(coverage), original);
});
test('partial zero result and legacy reports retain the warning', () => {
  const html = render({ status: 'partial' });
  assert.ok(html.includes('零条影响也不表示整个项目确定无影响'));
  assert.ok(!html.includes('源码解析：'));
  assert.equal(render({ status: 'complete' }), '');
});
test('zero and syntax-error counts are shown accurately without invented percentages', () => {
  const html = render({ status: 'partial', details: { parsed_python_files: 0, python_files: 2,
    resolved_call_count: 0, unresolved_call_count: 0, excluded_call_count: 0 } });
  assert.ok(html.includes('0 / 2'));
  assert.ok(html.includes('已确认 0 处'));
  assert.ok(!html.includes('另有'));
  assert.ok(!html.includes('%'));
});
test('invalid or missing detail counts are not rendered as trusted facts', () => {
  const html = render({ status: 'partial', details: { parsed_python_files: '<script>', python_files: 3,
    resolved_call_count: -1, unresolved_call_count: null } });
  assert.ok(!html.includes('源码解析：'));
  assert.ok(!html.includes('调用关系：'));
  assert.ok(html.includes('分析范围不完整'));
});
