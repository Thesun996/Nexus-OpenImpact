import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';

let server, CoverageNotice, ErrorNotice, ProjectDiagnostics;
before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), configFile: false,
    cacheDir: 'node_modules/.vite-coverage', logLevel: 'silent', server: { middlewareMode: true }, appType: 'custom' });
  ({ CoverageNotice, ErrorNotice } = await server.ssrLoadModule('/src/pages/PageParts.jsx'));
  ({ ProjectDiagnostics } = await server.ssrLoadModule('/src/components/workflow/WorkflowParts.jsx'));
});
after(async () => { await server?.close(); });
const render = coverage => renderToStaticMarkup(createElement(CoverageNotice, { coverage }));

test('partial report separates source parsing from call resolution without claiming complete coverage', () => {
  const coverage = { status: 'partial', details: { parsed_python_files: 65, python_files: 65,
    resolved_call_count: 478, unresolved_call_count: 5754, excluded_call_count: 63 } };
  const original = JSON.stringify(coverage), html = render(coverage);
  for (const text of ['结果基于已确认的代码关系', '65 / 65', '已确认 478 处', '尚未确认 5754 处',
    '63 个调用', '数量不等于本次变更的漏检数', '源码解析成功不代表所有调用关系均已确认']) assert.ok(html.includes(text), text);
  const intro = html.slice(0, html.indexOf('<details'));
  assert.doesNotMatch(intro, /65|478|5754|源码解析：|调用关系：/);
  assert.match(html, /<details class="oi-coverage-notice">/);
  assert.doesNotMatch(html, /<details[^>]*\bopen/);
  assert.equal(JSON.stringify(coverage), original);
});
test('partial zero result and legacy reports retain the warning', () => {
  const html = render({ status: 'partial' });
  assert.ok(html.includes('不能据此判断整个项目无影响'));
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
  assert.ok(html.includes('部分关系待确认'));
});

test('compact coverage starts collapsed while retaining the real scope and zero-result caveat', () => {
  const coverage = { status: 'partial', message: '此项目含未确认的静态调用。', details: { parsed_python_files: 2, python_files: 3 } };
  const original = JSON.stringify(coverage);
  const html = renderToStaticMarkup(createElement(CoverageNotice, { coverage, compact: true }));
  assert.match(html, /^<details class="oi-coverage-notice">/);
  assert.doesNotMatch(html, /<details[^>]*\bopen/);
  assert.match(html, /<summary>.*分析详情.*1 个文件未解析.*展开查看.*<\/summary>/);
  for (const text of [coverage.message, '2 / 3', '不能据此判断整个项目无影响']) assert.ok(html.includes(text));
  assert.equal(JSON.stringify(coverage), original);
  assert.equal(renderToStaticMarkup(createElement(CoverageNotice, { coverage: { status: 'complete' }, compact: true })), '');
});

test('report scope stays visible without an alert banner while configuration errors remain alerts', () => {
  const notice = render({ status: 'partial' });
  assert.match(notice, /^<section class="oi-coverage-summary" aria-label="分析范围">/);
  assert.ok(notice.includes('结果基于已确认的代码关系，未确认部分可在「分析详情」查看。'));
  assert.doesNotMatch(notice, /role="alert"/);
  const error = { code: 'invalid_change', message: '参数名称无效', diagnostics: [{ code: 'invalid_signature', message: '默认参数后不能出现必填位置参数' }] };
  const html = renderToStaticMarkup(createElement(ErrorNotice, { error }));
  assert.match(html, /^<section[^>]*role="alert"/);
  assert.ok(html.includes(error.message));
  assert.ok(html.includes(error.diagnostics[0].message));
});

test('legacy backend scope wording appears once inside collapsed details, without changing its value', () => {
  const coverage = { status: 'partial', message: '分析范围不完整；结果仅覆盖成功解析的代码。' };
  const before = JSON.stringify(coverage);
  const html = render(coverage);
  assert.equal((html.match(/分析范围不完整/g) || []).length, 1);
  assert.ok(html.indexOf(coverage.message) > html.indexOf('</summary>'));
  assert.doesNotMatch(html, /<details[^>]*\bopen/);
  assert.equal(JSON.stringify(coverage), before);
});

test('project diagnostics are collapsed without dropping positions or partial status', () => {
  const diagnostics = { unresolved_imports: [{ code: 'unresolved_import', file: 'client.py', line: 3, reason: '无法确认项目内目标模块' }] };
  const html = renderToStaticMarkup(createElement(ProjectDiagnostics, { diagnostics, coverage: { status: 'partial' } }));
  assert.match(html, /^<details class="oi-project-diagnostics">/);
  assert.ok(html.includes('1 条记录 · 部分关系待确认'));
  assert.ok(html.includes('client.py:3'));
});

test('source parse failures remain expanded, distinct from folded uncertain relationships', () => {
  const diagnostics = { parse_errors: [{ code: 'syntax_error', file: 'broken.py', line: 1, reason: '源码语法错误' }] };
  const html = renderToStaticMarkup(createElement(ProjectDiagnostics, { diagnostics, coverage: { status: 'partial' } }));
  assert.match(html, /^<details class="oi-project-diagnostics" open="">/);
  assert.ok(html.includes('broken.py:1'));
  const compact = renderToStaticMarkup(createElement(CoverageNotice, { coverage: { status: 'partial' }, compact: true }));
  assert.ok(compact.includes('部分关系待确认'));
});
