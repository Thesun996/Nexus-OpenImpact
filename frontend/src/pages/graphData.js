const list = (value) => Array.isArray(value) ? value : []

function addNode(nodes, id, role = 'path') {
  if (!id || nodes.has(id)) return
  nodes.set(id, { id, label: id, role })
}

export function buildEvidenceGraph(report) {
  const nodes = new Map()
  const edges = new Map()
  if (!report || report.change_domain && report.change_domain !== 'function') return { nodes: [], edges: [], supported: false }

  const addPath = (symbols, callSites, impactType, evidence) => {
    const ids = list(symbols)
    ids.forEach((id, index) => addNode(nodes, id, index === ids.length - 1 ? 'target' : impactType === 'direct' && index === 0 ? 'direct' : 'upstream'))
    ids.slice(0, -1).forEach((source, index) => {
      const target = ids[index + 1]
      const location = callSites[index] || null
      const key = `${source}->${target}@${location?.file || ''}:${location?.line || ''}`
      if (!edges.has(key)) edges.set(key, { id: key, source, target, impactType, location, evidence })
    })
  }

  list(report.direct_impacts).forEach((finding, index) => {
    addPath([finding.caller_symbol_id, finding.target_symbol_id], [finding], 'direct', list(report.evidences)[index])
  })
  list(report.indirect_impacts).forEach((finding, index) => {
    const evidence = list(report.evidences)[list(report.direct_impacts).length + index]
    list(evidence?.propagation_path).forEach(path => addPath(path.symbols, path.call_sites, finding.impact_type, evidence))
  })
  const graphEdges = [...edges.values()]
  const outgoing = new Map()
  graphEdges.forEach(edge => {
    if (!outgoing.has(edge.source)) outgoing.set(edge.source, [])
    outgoing.get(edge.source).push(edge.target)
  })
  const incoming = new Set(graphEdges.map(edge => edge.target))
  const starts = [...nodes.keys()].filter(id => !incoming.has(id))
  function longestPath(id, seen = new Set()) {
    if (seen.has(id)) return [id]
    const next = (outgoing.get(id) || []).filter(target => !seen.has(target))
    if (!next.length) return [id]
    const nextSeen = new Set(seen).add(id)
    return next.map(target => [id, ...longestPath(target, nextSeen)]).sort((left, right) => right.length - left.length)[0]
  }
  const orderedIds = starts.flatMap(start => longestPath(start)).filter((id, index, all) => all.indexOf(id) === index)
  const remaining = [...nodes.keys()].filter(id => !orderedIds.includes(id))
  const orderedNodes = [...orderedIds, ...remaining].map(id => nodes.get(id))
  return { nodes: orderedNodes, edges: graphEdges, supported: true }
}

export function buildProjectGraph(payload, report = null) {
  const rawNodes = list(payload?.graph?.nodes)
  const rawEdges = list(payload?.graph?.edges)
  if (!rawNodes.length) return { nodes: [], edges: [], supported: false, unresolved: list(payload?.diagnostics?.unresolved_calls) }
  const target = report?.change?.target_symbol_id
  const directCallers = new Set(list(report?.direct_impacts).map(item => item.caller_symbol_id))
  const nodes = rawNodes.map(node => ({
    id: node.id,
    label: node.id,
    role: node.id === target ? 'target' : directCallers.has(node.id) ? 'direct' : 'upstream',
    file: node.file,
    line: node.line,
  }))
  const edges = rawEdges.map(edge => ({
    ...edge,
    impactType: edge.target === target ? 'direct' : 'upstream',
    location: edge.location || null,
    evidence: null,
  }))
  return { nodes, edges, supported: true, unresolved: list(payload?.diagnostics?.unresolved_calls), coverage: payload.coverage }
}
