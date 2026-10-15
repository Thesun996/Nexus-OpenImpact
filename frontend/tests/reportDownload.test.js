import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildReportDownload, downloadReport } from '../src/pages/reportDownload.js';

for (const filename of ['analyze-response.json', 'module/analyze-response.json', 'symbol-report-response.json']) {
  test(`download preserves the full ${filename} report without modifying evidence`, () => {
    const report = JSON.parse(readFileSync(new URL(`../../docs/api-samples/${filename}`, import.meta.url)));
    const before = JSON.stringify(report);
    const exported = buildReportDownload(report);
    assert.deepEqual(JSON.parse(exported.content), report);
    assert.equal(JSON.stringify(report), before);
    assert.ok(exported.filename.endsWith('.json'));
  });
}

test('download filenames are bounded and cannot contain paths or control characters', () => {
  const report = { project_name: '../../项目\\name\n<script>|.exe', project_fingerprint: 'a'.repeat(64), summary: {} };
  const { filename } = buildReportDownload(report);
  assert.ok(filename.startsWith('openimpact-项目-name-script-.exe-'));
  assert.ok(!/[\\/<>|\n\r]/.test(filename));
  assert.ok(buildReportDownload(report, { projectName: 'x'.repeat(1000) }).filename.length < 110);
  assert.ok(buildReportDownload(report, { mode: 'demo' }).filename.startsWith('openimpact-demo-'));
  assert.ok(buildReportDownload(report, { reportId: 'b'.repeat(32) }).filename.endsWith(`-${'b'.repeat(16)}.json`));
});

test('missing or unserializable data cannot silently download an empty successful report', () => {
  for (const report of [null, undefined, [], 'report']) assert.throws(() => buildReportDownload(report));
  const cycle = {}; cycle.self = cycle;
  assert.throws(() => buildReportDownload(cycle));
});

test('browser download uses the JSON blob and releases its URL even when click fails', async t => {
  const originalDocument = globalThis.document;
  let blob, clicked = false, removed = false, released = false, cleanup;
  const anchor = { click: () => { clicked = true; }, remove: () => { removed = true; } };
  globalThis.document = { createElement: () => anchor, body: { appendChild: () => {} } };
  t.after(() => { if (originalDocument === undefined) delete globalThis.document; else globalThis.document = originalDocument; });
  t.mock.method(URL, 'createObjectURL', value => { blob = value; return 'blob:test-report'; });
  t.mock.method(URL, 'revokeObjectURL', value => { assert.equal(value, 'blob:test-report'); released = true; });
  t.mock.method(globalThis, 'setTimeout', callback => { cleanup = callback; });
  downloadReport({ summary: { direct_impact_count: 0 }, evidences: [] });
  assert.equal(clicked && removed, true);
  assert.equal(anchor.href, 'blob:test-report');
  assert.deepEqual(JSON.parse(await blob.text()), { summary: { direct_impact_count: 0 }, evidences: [] });
  cleanup(); assert.equal(released, true);
  removed = false; released = false;
  anchor.click = () => { throw new Error('download unavailable'); };
  assert.throws(() => downloadReport({ summary: {} }));
  assert.equal(removed, true);
  cleanup(); assert.equal(released, true);
});
