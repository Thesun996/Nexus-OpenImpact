import { correspondingEvidence, reportFindings } from './reportData.js'

const list = (value) => Array.isArray(value) ? value : []
const impactPriority = { call: 0, indirect_2hop: 1, indirect_1hop: 2, direct: 3 }
const rolePriority = { function: 0, upstream: 1, direct: 2, target: 3 }

function callIdentity(source, target, location) {
  if (!source || !target || !location?.file || location.line == null || location.column == null) return null
  return JSON.stringify([source, target, location.file, location.line, location.column])
}

function addNode(nodes, id, role) {
  if (!id) return
  const existing = nodes.get(id)
  if (!existing || rolePriority[role] > rolePriority[existing.role]) nodes.set(id, { id, label: id, role })
}

export function buildEvidenceGraph(report) {
  const nodes = new Map()
  const edges = new Map()
  const paths = new Map()
  if (!report || report.change_domain && report.change_domain !== 'function') return { nodes: [], edges: [], paths: [], supported: false }

  const addPath = (symbols, callSites, impactType, evidence) => {
    const ids = list(symbols)
    const calls = list(callSites)
    if (ids.length < 2 || calls.length !== ids.length - 1) return
    const keys = calls.map((call, index) => callIdentity(ids[index], ids[index + 1], call))
    if (keys.some(key => key == null)) return
    const pathId = JSON.stringify(keys)
    if (!paths.has(pathId)) paths.set(pathId, { id: pathId, symbols: ids, callSites: calls, impactType, evidence })
    ids.forEach((id, index) => addNode(nodes, id, index === ids.length - 1 ? 'target' : impactType === 'direct' && index === 0 ? 'direct' : 'upstream'))
    keys.forEach((key, index) => {
      const upstreamDepth = ids.length - index - 2
      const edgeImpact = impactType === 'direct' ? 'direct' : upstreamDepth === 0 ? 'call' : upstreamDepth === 1 ? 'indirect_1hop' : 'indirect_2hop'
      const existing = edges.get(key)
      if (!existing || impactPriority[edgeImpact] > impactPriority[existing.impactType]) {
        edges.set(key, { id: key, source: ids[index], target: ids[index + 1], impactType: edgeImpact, location: calls[index], evidence })
      }
    })
  }

  reportFindings(report).forEach((finding, index) => {
    const evidence = correspondingEvidence(report, index, finding)
    if (finding.impact_type === 'direct') {
      addPath([finding.caller_symbol_id, finding.target_symbol_id], [finding], 'direct', evidence)
    } else if (evidence) {
      list(evidence.propagation_path).forEach(path => addPath(path.symbols, path.call_sites, finding.impact_type, evidence))
    }
  })
  // Preserve a readable node order without inferring a new path between branches.
  const orderedIds = new Set([...paths.values()].sort((left, right) => right.symbols.length - left.symbols.length).flatMap(path => path.symbols))
  return { nodes: [...orderedIds].map(id => nodes.get(id)), edges: [...edges.values()], paths: [...paths.values()], supported: true }
}

export function buildProjectGraph(payload, report = null) {
  const rawNodes = list(payload?.graph?.nodes)
  const rawEdges = list(payload?.graph?.edges)
  const diagnostics = payload?.diagnostics && typeof payload.diagnostics === 'object' && !Array.isArray(payload.diagnostics) ? payload.diagnostics : {}
  if (!rawNodes.length) return { nodes: [], edges: [], paths: [], supported: false, diagnostics, unresolved: list(diagnostics.unresolved_calls) }
  const evidenceGraph = buildEvidenceGraph(report)
  const findingsByCall = new Map(evidenceGraph.edges.map(edge => [callIdentity(edge.source, edge.target, edge.location), edge]))
  const target = evidenceGraph.supported ? report?.change?.target_symbol_id : null
  const edges = rawEdges.map(edge => {
    const finding = findingsByCall.get(callIdentity(edge.source, edge.target, edge.location))
    return { ...edge, impactType: finding?.impactType || 'call', location: edge.location || null, evidence: finding?.evidence || null }
  })
  const directCallers = new Set(edges.filter(edge => edge.impactType === 'direct').map(edge => edge.source))
  const upstreamCallers = new Set(edges.filter(edge => edge.impactType.startsWith('indirect_')).map(edge => edge.source))
  const nodes = rawNodes.map(node => ({
    id: node.id,
    label: node.id,
    kind: node.kind,
    role: node.id === target ? 'target' : directCallers.has(node.id) ? 'direct' : upstreamCallers.has(node.id) ? 'upstream' : 'function',
    file: node.file,
    line: node.line,
  }))
  return { nodes, edges, paths: evidenceGraph.paths, supported: true, diagnostics, unresolved: list(diagnostics.unresolved_calls), coverage: payload.coverage }
}
