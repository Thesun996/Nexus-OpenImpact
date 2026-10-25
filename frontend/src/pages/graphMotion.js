export function clampGraphPosition(point, width, height) {
  return {
    x: Math.max(40, Math.min(width - 40, point.x)),
    y: Math.max(40, Math.min(height - 60, point.y)),
  }
}

// Stable phases keep nodes from moving in unison; offsets never accumulate.
export function floatingPosition(item, elapsed, width, height, paused = false) {
  let seed = 0
  for (const char of item.node.id) seed = (seed * 31 + char.codePointAt(0)) >>> 0
  const phase = (seed % 360) * Math.PI / 180
  const cycle = (9000 + seed % 4000) / (2 * Math.PI)
  const origin = item.motionOrigin ?? 0
  const dx = paused ? 0 : 4 * (Math.sin(elapsed / cycle + phase) - Math.sin(origin / cycle + phase))
  const dy = paused ? 0 : 6 * (Math.sin(elapsed / (cycle * 1.17) + phase * 2) - Math.sin(origin / (cycle * 1.17) + phase * 2))
  return { ...item, ...clampGraphPosition({ x: item.x + dx, y: item.y + dy }, width, height) }
}

function nodeSeed(id) {
  let seed = 0
  for (const char of id) seed = (seed * 31 + char.codePointAt(0)) >>> 0
  return seed
}

export function simulateGraphStep(items, edges, elapsed, width, height, options = {}) {
  const draggingId = options.draggingId ?? null
  const frameScale = Math.min(options.frameScale ?? 1, 2)
  const next = items.map(item => ({ ...item, vx: item.vx ?? 0, vy: item.vy ?? 0 }))
  const indexById = new Map(next.map((item, index) => [item.node.id, index]))
  const forces = next.map(() => ({ x: 0, y: 0 }))

  for (let left = 0; left < next.length; left += 1) {
    for (let right = left + 1; right < next.length; right += 1) {
      const dx = next[right].x - next[left].x
      const dy = next[right].y - next[left].y
      const distanceSquared = Math.max(dx * dx + dy * dy, 900)
      const distance = Math.sqrt(distanceSquared)
      const strength = 6800 / distanceSquared
      const forceX = dx / distance * strength
      const forceY = dy / distance * strength
      forces[left].x -= forceX
      forces[left].y -= forceY
      forces[right].x += forceX
      forces[right].y += forceY
    }
  }

  for (const edge of edges) {
    const sourceIndex = indexById.get(edge.source)
    const targetIndex = indexById.get(edge.target)
    if (sourceIndex == null || targetIndex == null) continue
    const source = next[sourceIndex]
    const target = next[targetIndex]
    const dx = target.x - source.x
    const dy = target.y - source.y
    const distance = Math.max(Math.hypot(dx, dy), 1)
    const stretch = (distance - 185) * 0.006
    const forceX = dx / distance * stretch
    const forceY = dy / distance * stretch
    forces[sourceIndex].x += forceX
    forces[sourceIndex].y += forceY
    forces[targetIndex].x -= forceX
    forces[targetIndex].y -= forceY
  }

  return next.map((item, index) => {
    if (item.node.id === draggingId) return { ...item, vx: 0, vy: 0 }
    const seed = nodeSeed(item.node.id)
    const phase = (seed % 360) * Math.PI / 180
    const homeX = item.homeX ?? item.x
    const homeY = item.homeY ?? item.y
    const wanderX = Math.sin(elapsed / (3100 + seed % 900) + phase) * 0.025
    const wanderY = Math.cos(elapsed / (3600 + seed % 1100) + phase * 1.7) * 0.025
    const centerX = width / 2
    const centerY = height / 2
    const forceX = forces[index].x + (homeX - item.x) * 0.0007 + (centerX - item.x) * 0.00015 + wanderX
    const forceY = forces[index].y + (homeY - item.y) * 0.0007 + (centerY - item.y) * 0.00015 + wanderY
    const vx = (item.vx + forceX * frameScale) * 0.91
    const vy = (item.vy + forceY * frameScale) * 0.91
    const position = clampGraphPosition({ x: item.x + vx * frameScale, y: item.y + vy * frameScale }, width, height)
    return {
      ...item,
      ...position,
      vx: position.x === item.x + vx * frameScale ? vx : vx * -0.25,
      vy: position.y === item.y + vy * frameScale ? vy : vy * -0.25,
    }
  })
}
