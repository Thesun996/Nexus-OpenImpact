import test, { after, before } from 'node:test'
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

let server, mergeProjects, projectSummary

before(async () => {
  server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), configFile: false,
    cacheDir: 'node_modules/.vite-project-library-tests', logLevel: 'silent', server: { middlewareMode: true }, appType: 'custom' })
  ;({ mergeProjects, projectSummary } = await server.ssrLoadModule('/src/pages/ProjectLibraryPage.jsx'))
})

after(async () => { await server?.close() })

test('project summary uses persisted snapshot counts without mutating it', () => {
  const snapshot = { python_file_count: 4, function_count: 4, coverage_status: 'complete' }
  const beforeText = JSON.stringify(snapshot)
  assert.equal(projectSummary(snapshot), 'Python 文件 4 · 函数 4 · 覆盖 完整')
  assert.equal(JSON.stringify(snapshot), beforeText)
  assert.equal(projectSummary(null), '暂无快照')
})

test('project pagination merge keeps order and drops duplicates', () => {
  const current = [{ id: 'project-a' }, { id: 'project-b' }]
  const incoming = [{ id: 'project-b' }, { id: 'project-c' }]
  assert.deepEqual(mergeProjects(current, incoming), [{ id: 'project-a' }, { id: 'project-b' }, { id: 'project-c' }])
  assert.deepEqual(current, [{ id: 'project-a' }, { id: 'project-b' }])
  assert.deepEqual(incoming, [{ id: 'project-b' }, { id: 'project-c' }])
})
