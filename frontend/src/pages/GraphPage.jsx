import { useEffect, useMemo, useRef, useState } from 'react'
import { useWorkflow } from '../state/WorkflowContext.jsx'
import { locationText, impactLabel } from '../components/report/presentation.js'
import { buildEvidenceGraph, buildProjectGraph } from './graphData.js'
import { apiClient } from '../api/client.js'
import { getProjectSource } from '../state/workflow.js'
import { useReducedMotionPreference } from '../motion/reducedMotion.js'
import { clampGraphPosition, simulateGraphStep } from './graphMotion.js'
import './graph.css'

const unresolvedReason = {
  name_not_indexed: '目标名称不在项目索引中',
  attribute_chain_unsupported: '属性调用链超出当前静态解析范围',
  unsupported_callee_expression: '调用目标是动态表达式',
  module_level_call: '模块顶层调用没有可归属的函数调用者',
  caller_not_indexed: '调用者不在当前函数索引中',
}

function layoutNodes(nodes, width, height) {
  const radiusX = Math.min(width * 0.34, 280)
  const radiusY = Math.min(height * 0.27, 125)
  const centerX = width / 2
  const centerY = height / 2 - 8
  return nodes.map((node, index) => {
    const angle = nodes.length === 1 ? 0 : -Math.PI / 2 + index * (Math.PI * 2 / nodes.length)
    const x = centerX + Math.cos(angle) * radiusX
    const y = centerY + Math.sin(angle) * radiusY
    return { node, x, y, homeX: x, homeY: y, vx: 0, vy: 0 }
  })
}

function GraphCanvas({ graph, selected, onSelect }) {
  const columns = Math.min(4, Math.max(1, graph.nodes.length))
  const width = Math.max(760, columns * 190); const height = Math.max(360, Math.ceil(graph.nodes.length / columns) * 130)
  const [positions, setPositions] = useState(() => layoutNodes(graph.nodes, width, height))
  const [draggingId, setDraggingId] = useState(null)
  const [manuallyPaused, setManuallyPaused] = useState(false)
  const [viewport, setViewport] = useState({ x: 0, y: 0, width, height })
  const motionTimeRef = useRef(0)
  const reducedMotion = useReducedMotionPreference()
  const svgRef = useRef(null)
  const dragRef = useRef(null)
  const panRef = useRef(null)
  useEffect(() => {
    setPositions(layoutNodes(graph.nodes, width, height))
    setViewport({ x: 0, y: 0, width, height })
    dragRef.current = null
    panRef.current = null
    setDraggingId(null)
  }, [graph.nodes, width, height])
  useEffect(() => {
    if (reducedMotion || manuallyPaused) return undefined
    const interval = window.setInterval(() => {
      if (document.hidden) return
      motionTimeRef.current += 1000 / 30
      setPositions(current => simulateGraphStep(current, graph.edges, motionTimeRef.current, width, height, {
        draggingId: dragRef.current?.id,
      }))
    }, 1000 / 30)
    return () => window.clearInterval(interval)
  }, [graph.edges, manuallyPaused, reducedMotion, width, height])
  const displayedPositions = positions
  const byId = new Map(displayedPositions.map(item => [item.node.id, item]))
  const pointFromEvent = event => {
    const svg = svgRef.current
    const matrix = svg?.getScreenCTM()
    if (!matrix) return null
    const point = svg.createSVGPoint()
    point.x = event.clientX
    point.y = event.clientY
    return point.matrixTransform(matrix.inverse())
  }
  const beginDrag = (event, node) => {
    if (event.button !== 0 || dragRef.current) return
    const item = byId.get(node.id)
    const point = pointFromEvent(event)
    if (!item || !point) return
    event.preventDefault()
    event.stopPropagation()
    dragRef.current = { id: node.id, pointerId: event.pointerId, target: event.currentTarget, offsetX: point.x - item.x, offsetY: point.y - item.y }
    event.currentTarget.setPointerCapture?.(event.pointerId)
    setPositions(current => current.map(position => position.node.id === node.id ? { ...position, x: item.x, y: item.y, vx: 0, vy: 0 } : position))
    setDraggingId(node.id)
    onSelect(node)
  }
  const beginPan = event => {
    if (event.button !== 0 || event.target !== svgRef.current || dragRef.current) return
    const point = pointFromEvent(event)
    if (!point) return
    panRef.current = { pointerId: event.pointerId, point, viewport }
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }
  const moveDrag = event => {
    const drag = dragRef.current
    if (!drag || event.pointerId !== drag.pointerId) {
      const pan = panRef.current
      if (!pan || event.pointerId !== pan.pointerId) return
      const point = pointFromEvent(event)
      if (!point) return
      setViewport({ ...pan.viewport, x: pan.viewport.x + pan.point.x - point.x, y: pan.viewport.y + pan.point.y - point.y })
      return
    }
    const point = pointFromEvent(event)
    if (!point) return
    setPositions(current => current.map(item => item.node.id !== drag.id ? item : {
      ...item,
      ...clampGraphPosition({ x: point.x - drag.offsetX, y: point.y - drag.offsetY }, width, height),
      vx: 0,
      vy: 0,
    }))
  }
  const endDrag = event => {
    const pan = panRef.current
    if (pan && event.pointerId === pan.pointerId) {
      panRef.current = null
      if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
      return
    }
    const drag = dragRef.current
    if (!drag || event.pointerId !== drag.pointerId) return
    dragRef.current = null
    setPositions(current => current.map(item => item.node.id === drag.id ? { ...item, homeX: item.x, homeY: item.y, vx: 0, vy: 0 } : item))
    setDraggingId(null)
    if (drag.target?.hasPointerCapture?.(drag.pointerId)) drag.target.releasePointerCapture(drag.pointerId)
  }
  const zoom = factor => {
    setViewport(current => {
      const nextWidth = Math.max(width * 0.48, Math.min(width * 1.8, current.width * factor))
      const nextHeight = nextWidth * height / width
      return { x: current.x + (current.width - nextWidth) / 2, y: current.y + (current.height - nextHeight) / 2, width: nextWidth, height: nextHeight }
    })
  }
  const resetView = () => {
    setPositions(layoutNodes(graph.nodes, width, height))
    setViewport({ x: 0, y: 0, width, height })
  }
  const handleWheel = event => {
    event.preventDefault()
    zoom(event.deltaY > 0 ? 1.1 : 0.9)
  }
  return <div className="oi-graph-canvas">
    <div className="oi-graph-tools" aria-label="关系图画布控制">
      <button type="button" title="放大" aria-label="放大关系图" onClick={() => zoom(0.86)}>+</button>
      <button type="button" title="缩小" aria-label="缩小关系图" onClick={() => zoom(1.16)}>−</button>
      <button type="button" title="恢复默认布局" aria-label="恢复默认布局" onClick={resetView}>↺</button>
      {!reducedMotion && <button type="button" title={manuallyPaused ? '继续动态布局' : '暂停动态布局'} aria-label={manuallyPaused ? '继续动态布局' : '暂停动态布局'} onClick={() => setManuallyPaused(value => !value)}>{manuallyPaused ? '▶' : 'Ⅱ'}</button>}
    </div>
    <svg ref={svgRef} viewBox={`${viewport.x} ${viewport.y} ${viewport.width} ${viewport.height}`} role="group" aria-label="基于证据的代码关系图" style={{ height: `${Math.min(640, height)}px` }} onPointerDown={beginPan} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag} onLostPointerCapture={endDrag} onWheel={handleWheel}>
      <defs><marker id="oi-graph-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L8,4 L0,8 z" /></marker><marker id="oi-graph-arrow-active" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L8,4 L0,8 z" /></marker></defs>
      <g className="oi-graph-edges">{graph.edges.map(edge => { const from = byId.get(edge.source); const to = byId.get(edge.target); if (!from || !to) return null; const active = selected && (edge.source === selected.id || edge.target === selected.id); const dx = to.x - from.x; const dy = to.y - from.y; const length = Math.max(Math.hypot(dx, dy), 1); const radius = 31; return <line className={active ? 'is-active' : ''} key={edge.id} x1={from.x + (dx / length) * radius} y1={from.y + (dy / length) * radius} x2={to.x - (dx / length) * radius} y2={to.y - (dy / length) * radius} markerEnd={`url(#oi-graph-arrow${active ? '-active' : ''})`} /> })}</g>
      {displayedPositions.map(({ node, x, y }) => <g key={node.id} className={`oi-graph-node is-${node.role} ${selected?.id === node.id ? 'is-selected' : ''} ${draggingId === node.id ? 'is-dragging' : ''}`} role="button" tabIndex="0" title={`${node.label}，可拖动`} aria-label={`${node.label}，可拖动节点`} onPointerDown={event => beginDrag(event, node)} onClick={() => onSelect(node)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(node) } }}>
        <circle cx={x} cy={y} r="27" /><text x={x} y={y + 46} textAnchor="middle">{node.label}</text>
      </g>)}
    </svg>
  </div>
}

export default function GraphPage({ navigate }) {
  const { state } = useWorkflow()
  const [projectPayload, setProjectPayload] = useState(null)
  const [graphError, setGraphError] = useState(null)
  const [selected, setSelected] = useState(null)
  useEffect(() => {
    const source = getProjectSource(state)
    if (state.mode === 'demo' || !source || !state.projectFingerprint) {
      setProjectPayload(null)
      setGraphError(null)
      setSelected(null)
      return undefined
    }
    const controller = new AbortController()
    setProjectPayload(null)
    setGraphError(null)
    setSelected(null)
    apiClient.relationGraph(source, { fingerprint: state.projectFingerprint, analysisRoot: state.analysisRoot, signal: controller.signal })
      .then(payload => setProjectPayload(payload))
      .catch(error => { if (error?.name !== 'AbortError') setGraphError(error?.message || '关系图读取失败。') })
    return () => controller.abort()
  }, [state.mode, state.file, state.snapshot, state.projectFingerprint, state.analysisRoot])
  const evidenceGraph = useMemo(() => buildEvidenceGraph(state.report), [state.report])
  const projectGraph = useMemo(() => buildProjectGraph(projectPayload, state.report), [projectPayload, state.report])
  const graph = projectGraph?.supported ? projectGraph : evidenceGraph
  const isFullGraph = projectGraph?.supported === true
  const unresolvedCount = projectGraph?.unresolved?.length || 0
  const selectedEdges = selected ? graph.edges.filter(edge => edge.source === selected.id || edge.target === selected.id) : graph.edges
  const selectedNode = selected ? graph.nodes.find(node => node.id === selected.id) : null
  useEffect(() => {
    if (selected && !selectedNode) setSelected(null)
  }, [selected, selectedNode])
  const unsupported = state.report && state.changeDomain && state.changeDomain !== 'function' && !projectGraph?.supported
  return <div className="oi-graph-page">
    <section className="page-heading"><div><h1>代码关系图</h1><p>{isFullGraph ? '展示当前项目中已由静态分析确认的函数调用关系' : '只展示当前分析报告中有静态证据支持的调用关系'}</p></div><div className="heading-actions"><button className="ghost-action" type="button" onClick={() => navigate(state.report ? 'report' : 'upload')}>{state.report ? '返回报告' : '开始分析'}</button></div></section>
    {graphError && <section className="state-message" role="status">完整项目关系图暂时读取失败：{graphError} 当前仍可查看分析报告中的证据关系。</section>}
    {!state.report && !projectGraph?.supported && <section className="detail-card empty-state-card"><h2>还没有可展示的关系</h2><p>请先读取项目 ZIP。关系图不会生成没有证据支持的节点或连线。</p></section>}
    {unsupported && <section className="state-message">当前报告属于 {state.changeDomain} 领域；第一版关系图暂只展示函数调用路径。</section>}
    {!unsupported && graph.nodes.length > 0 && <>
      <section className="oi-graph-stats"><div><b>{graph.nodes.length}</b><span>证据节点</span></div><div><b>{graph.edges.length}</b><span>调用关系</span></div><div><b>{graph.edges.filter(edge => edge.impactType === 'direct').length}</b><span>直接关系</span></div><div><b>{unresolvedCount || graph.edges.filter(edge => edge.impactType !== 'direct').length}</b><span>{unresolvedCount ? '待人工检查' : '上游待检查'}</span></div></section>
      <section className="oi-graph-layout"><div><GraphCanvas graph={graph} selected={selected} onSelect={setSelected} /><div className="oi-graph-legend"><span className="is-target">目标函数</span><span className="is-direct">直接调用</span><span className="is-upstream">上游调用</span></div>{isFullGraph ? <section className="oi-graph-chain"><h2>项目函数清单</h2><div className="oi-graph-chain-items">{graph.nodes.map(node => <b key={node.id} className={`is-${node.role}`}>{node.label}</b>)}</div><p>节点来自项目 AST 索引，连线来自可静态解析的显式函数调用。未解析调用不会被画成确定关系。</p></section> : <section className="oi-graph-chain"><h2>当前影响链</h2><div className="oi-graph-chain-items">{graph.nodes.map((node, index) => <span key={node.id}><b className={`is-${node.role}`}>{node.label}</b>{index < graph.nodes.length - 1 && <i aria-hidden="true">→</i>}</span>)}</div><p>链条只由本次报告中的静态调用证据组成；它不是完整项目依赖图。</p></section>}</div><aside className="oi-graph-evidence"><h2>{selected ? selected.label : '关系证据'}</h2>{selectedNode && <p className="oi-graph-location">定义位置：{selectedNode.file || '位置未提供'}:{selectedNode.line ?? '—'}</p>}{selected ? <p>该节点关联的已确认调用关系如下。</p> : <p>点击图中的节点，查看与它相关的静态证据。</p>}{selectedEdges.map(edge => <button className="oi-graph-edge" key={edge.id} type="button" onClick={() => setSelected(graph.nodes.find(node => node.id === edge.target))}><strong>{edge.source} → {edge.target}</strong><span>{impactLabel(edge.impactType)} · {locationText(edge.location)}</span></button>)}{selected && !selectedEdges.length && <p className="oi-graph-empty-detail">当前没有已确认的调用边连接到这个节点。</p>}</aside></section>
    </>}
    {isFullGraph && unresolvedCount > 0 && <section className="oi-graph-unresolved"><div><h2>待人工检查的调用</h2><p>这些调用已被 AST 发现，但当前无法证明目标函数，因此没有画成确定关系。</p></div><div className="oi-graph-unresolved-list">{projectGraph.unresolved.map(item => <div key={`${item.file}:${item.line}:${item.column}:${item.expression}`}><strong>{item.expression}()</strong><span>{item.file}:{item.line}{item.column != null ? `:${item.column}` : ''}</span><small>{unresolvedReason[item.reason] || item.reason || '静态解析未确认'}</small></div>)}</div></section>}
  </div>
}
