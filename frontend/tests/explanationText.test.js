import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';

let server, ExplanationText;
before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)),
    configFile: false, logLevel: 'silent', server: { middlewareMode: true }, appType: 'custom' });
  ExplanationText = (await server.ssrLoadModule('/src/components/report/ExplanationText.jsx')).default;
});
after(async () => { await server?.close(); });

test('source-backed checks render in order with separate boundary text', () => {
  const html = renderToStaticMarkup(createElement(ExplanationText, {
    text: '1. 先看 report.py:5\n2. 再看 page.py:5\n覆盖不完整，请人工检查。', ordered: true,
  }));
  assert.ok(html.includes('<ol><li>先看 report.py:5</li><li>再看 page.py:5</li></ol>'));
  assert.ok(html.includes('<p>覆盖不完整，请人工检查。</p>'));
});

test('model and source text is escaped and old single paragraph remains readable', () => {
  const html = renderToStaticMarkup(createElement(ExplanationText, {
    text: '<img src=x onerror=alert(1)>\n已有证据，没有执行源码。',
  }));
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('&lt;img'));
  assert.ok(html.includes('<p>已有证据，没有执行源码。</p>'));
});
