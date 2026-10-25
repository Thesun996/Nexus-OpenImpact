import test from 'node:test'
import assert from 'node:assert/strict'
import { createGraphLayout, defaultGraphViewport, zoomGraphViewport } from '../src/pages/graphMotion.js'

test('large graphs keep every node with a readable viewport independent of total node count', () => {
  for (const count of [100, 505]) {
    const nodes = Array.from({ length: count }, (_, index) => ({ id: `many.f${index}` }))
    const layout = createGraphLayout(nodes)
    assert.equal(layout.positions.length, count)
    assert.equal(new Set(layout.positions.map(item => `${item.x}:${item.y}`)).size, count)
    assert.deepEqual(layout.positions.map(item => item.node.id), nodes.map(node => node.id))
    assert.equal(layout.animated, false)
    for (const width of [278, 731]) {
      const viewport = defaultGraphViewport(layout, { width, height: 480 })
      assert.equal(viewport.width, width)
      assert.equal(viewport.height, 480)
      assert.equal(16 * Math.min(width / viewport.width, 480 / viewport.height), 16)
    }
  }
})

test('zoom preserves viewport aspect ratio and center at desktop and mobile sizes', () => {
  for (const width of [278, 731]) {
    const size = { width, height: 480 }
    const initial = { x: 120, y: 240, ...size }
    let viewport = initial
    for (let step = 0; step < 25; step++) viewport = zoomGraphViewport(viewport, 0.86, size)
    assert.equal(viewport.width, width / 4)
    assert.ok(Math.abs(viewport.width / viewport.height - width / 480) < 1e-9)
    assert.ok(Math.abs(viewport.x + viewport.width / 2 - (initial.x + width / 2)) < 1e-9)
    assert.ok(Math.abs(viewport.y + viewport.height / 2 - (initial.y + 240)) < 1e-9)
  }
})

test('small graph layout stays inside its world and can retain the original gentle motion', () => {
  for (const count of [1, 4, 12]) {
    const layout = createGraphLayout(Array.from({ length: count }, (_, index) => ({ id: `f${index}` })))
    assert.equal(layout.animated, true)
    assert.ok(layout.positions.every(item => item.x >= 40 && item.x <= layout.width - 40 && item.y >= 40 && item.y <= layout.height - 60))
  }
})
