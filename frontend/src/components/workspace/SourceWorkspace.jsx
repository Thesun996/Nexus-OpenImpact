import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { apiClient } from '../../api/client.js'
import { useWorkflow } from '../../state/WorkflowContext.jsx'
import { getProjectSource } from '../../state/workflow.js'
import { createRequestGate, sourceTree } from './requestGate.js'
import './workspace.css'

const SourceContext = createContext(null)
const PAGE_LINES = 200
export const useSourceWorkspace = () => useContext(SourceContext)

export function SourceLink({ location, sourceHash }) {
  const workspace = useSourceWorkspace()
  if (!workspace?.snapshot.source || !workspace.snapshot.fingerprint || !location?.file) return null
  return <button type="button" className="oi-source-link" onClick={() => workspace.openFile(location.file, location.line, sourceHash)}>打开完整源码</button>
}

function Folder({ node, select, selected }) {
  return <ul className="oi-source-tree">{Object.entries(node.directories).map(([name, child]) => <li key={name}><details open><summary>{name}</summary><Folder node={child} select={select} selected={selected} /></details></li>)}
    {node.files.map(file => <li key={file.path}><button type="button" title={file.path} aria-pressed={selected === file.path} onClick={() => select(file.path)}>{file.path.split('/').at(-1)}</button></li>)}</ul>
}

export default function SourceWorkspace({ children }) {
  const { state } = useWorkflow()
  const source = useMemo(() => getProjectSource(state), [state.file, state.snapshot])
  const scope = useMemo(() => ({}), [source, state.projectFingerprint, state.analysisRoot])
  const latestScope = useRef(scope); latestScope.current = scope
  const snapshot = { source, fingerprint: state.projectFingerprint, analysisRoot: state.analysisRoot,
    mode: state.mode, revision: state.revision, report: state.report, change: state.validatedChange?.payload }
  const [open, setOpen] = useState(false)
  const [reading, setReading] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [line, setLine] = useState(1)
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const [fileFilter, setFileFilter] = useState('')
  const gate = useRef(createRequestGate())
  const cache = useRef(new Map())
  const dialog = useRef(null)
  const code = useRef(null)
  const current = reading?.scope === scope ? reading.payload : null

  useEffect(() => {
    gate.current.cancel(); cache.current.clear(); setReading(null); setError(null); setLoading(false)
    setOpen(false); setSearch(''); setFileFilter(''); setPage(0); setLine(1)
    return () => gate.current.cancel()
  }, [scope])
  useEffect(() => {
    if (open && !dialog.current?.open) dialog.current?.showModal()
    if (!open && dialog.current?.open) dialog.current.close()
    if (!open) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previousOverflow }
  }, [open])
  useEffect(() => {
    const container = code.current, target = container?.querySelector('.is-target-line')
    if (!target) return
    // Scroll only the code viewport, keeping the folder list and page stable.
    const bounds = container.getBoundingClientRect(), row = target.getBoundingClientRect()
    if (row.top < bounds.top) container.scrollTop += row.top - bounds.top
    else if (row.bottom > bounds.bottom) container.scrollTop += row.bottom - bounds.bottom
  }, [line, page, current?.file?.path])

  async function openFile(path, targetLine = 1, expectedHash) {
    if (!snapshot.source || !snapshot.fingerprint) return
    setOpen(true); setError(null); setLine(targetLine || 1); setPage(Math.floor(Math.max(0, targetLine - 1) / PAGE_LINES)); setSearch('')
    const request = gate.current.begin()
    const requestedScope = scope
    const apply = payload => {
      if (payload.project_fingerprint !== snapshot.fingerprint || (expectedHash && payload.file?.source_hash !== expectedHash))
        throw new Error('项目或源码与当前证据不一致，请重新读取项目并分析。')
      if (!Array.isArray(payload.files) || (path && (payload.file?.path !== path || typeof payload.file.content !== 'string')))
        throw new Error('源码响应不完整，请重试。')
      setReading({ scope: requestedScope, payload })
    }
    if (cache.current.has(path || '')) {
      try { apply(cache.current.get(path || '')); setLoading(false) } catch (failure) {
        setReading(null); setLoading(false); setError(failure.message)
      }
      return
    }
    setLoading(true)
    // Hide the old file while the requested file is being read.
    setReading(previous => previous?.scope === scope ? { scope, payload: { ...previous.payload, file: null } } : null)
    try {
      const payload = await apiClient.source(snapshot.source, snapshot.fingerprint, { path, analysisRoot: snapshot.analysisRoot, signal: request.controller.signal })
      if (!gate.current.current(request) || latestScope.current !== requestedScope) return
      apply(payload); cache.current.set(path || '', payload)
    } catch (failure) {
      if (gate.current.current(request) && latestScope.current === requestedScope && failure.name !== 'AbortError') setError(failure.message)
    } finally {
      if (gate.current.current(request) && latestScope.current === requestedScope) setLoading(false)
    }
  }
  const files = (current?.files || []).filter(file => file.path.toLowerCase().includes(fileFilter.toLowerCase()))
  const lines = current?.file?.content ? current.file.content.split(/\r\n|\n|\r/) : []
  if (lines.at(-1) === '' && lines.length > 1) lines.pop()
  function findNext(event) {
    event.preventDefault()
    if (!search) return
    const matches = lines.flatMap((text, index) => text.includes(search) ? [index + 1] : [])
    const next = matches.find(value => value > line) || matches[0]
    if (next) { setLine(next); setPage(Math.floor((next - 1) / PAGE_LINES)); setError(null) }
    else setError('当前文件中没有匹配的文字。')
  }
  return <SourceContext.Provider value={{ snapshot, openFile }}>
    {children}
    <button className="oi-source-launcher" type="button" title="浏览当前项目的 Python 源码" aria-label="打开项目源码" disabled={!snapshot.source || !snapshot.fingerprint}
      onClick={() => { setOpen(true); if (!current) void openFile() }}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h7l2 3h9v11H3z" /><path d="m10 12-3 3 3 3m4-6 3 3-3 3" /></svg><span>项目源码</span></button>
    <dialog className="oi-source-dialog" ref={dialog} aria-labelledby="oi-source-title" onClose={() => setOpen(false)} onCancel={() => { gate.current.cancel(); setLoading(false); setOpen(false) }}>
      <header><div><h2 id="oi-source-title">项目源码</h2><p>只读阅读 · 文件可打开不代表已完整分析</p></div><button type="button" className="ghost-action" onClick={() => { gate.current.cancel(); setLoading(false); setOpen(false) }}>关闭源码</button></header>
      <div className="oi-source-layout"><aside aria-label="Python 文件目录"><label htmlFor="oi-file-filter">查找文件</label><input id="oi-file-filter" value={fileFilter} onChange={event => setFileFilter(event.target.value)} placeholder="文件名或路径" />
        <Folder node={sourceTree(files)} select={path => void openFile(path)} selected={current?.file?.path} />{!files.length && <p>{loading ? '正在读取目录…' : '没有匹配的 Python 文件。'}</p>}</aside>
        <section className="oi-source-reading" aria-label="完整源码阅读区">
          {error && <p className="state-message error" role="alert">{error}<button type="button" className="oi-source-link" onClick={() => void openFile()}>重新读取目录</button></p>}
          {loading && <p role="status">正在读取所选 ZIP 的源码…</p>}
          {current?.file ? <><h3 title={current.file.path}>{current.file.path}</h3><form className="oi-source-search" onSubmit={findNext}><label htmlFor="oi-code-search">文件内查找</label><input id="oi-code-search" value={search} onChange={event => setSearch(event.target.value)} /><button type="submit">下一个匹配</button></form>
            <div className="oi-source-pagination"><button type="button" disabled={!page} onClick={() => setPage(value => value - 1)}>上一段</button><span>{lines.length ? `${page * PAGE_LINES + 1}–${Math.min(lines.length, (page + 1) * PAGE_LINES)} / ${lines.length} 行` : '空文件 · 0 行'}</span><button type="button" disabled={(page + 1) * PAGE_LINES >= lines.length} onClick={() => setPage(value => value + 1)}>下一段</button></div>
            <div className="oi-full-source" ref={code} tabIndex={0} aria-label="源码，可横向滚动"><pre>{lines.slice(page * PAGE_LINES, (page + 1) * PAGE_LINES).map((text, offset) => <span className={page * PAGE_LINES + offset + 1 === line ? 'is-target-line' : ''} key={offset}><b aria-hidden="true">{page * PAGE_LINES + offset + 1}</b><code>{text || ' '}</code></span>)}</pre></div>
            <details><summary>文件技术信息</summary><p>编码：{current.file.encoding}</p><p className="oi-source-hash">SHA-256：{current.file.source_hash}</p></details>
          </> : !loading && <p>从目录中选择一个 Python 文件。源码不会被执行或修改。</p>}
        </section></div>
    </dialog>
  </SourceContext.Provider>
}
