import test from 'node:test'
import assert from 'node:assert/strict'
import { discardExit, motionCurve, pageDirection } from '../src/motion/pageTransition.js'
import { createInitialState, workflowReducer } from '../src/state/workflow.js'
import { reducedMotionSnapshot, subscribeReducedMotion } from '../src/motion/reducedMotion.js'

test('motion preference follows live media changes and cleans up its listener', () => {
  const previousWindow = globalThis.window
  const listeners = new Set()
  const media = {
    matches: false,
    addEventListener: (type, listener) => { assert.equal(type, 'change'); listeners.add(listener) },
    removeEventListener: (type, listener) => { assert.equal(type, 'change'); listeners.delete(listener) },
  }
  globalThis.window = { matchMedia: (query) => { assert.equal(query, '(prefers-reduced-motion: reduce)'); return media } }
  try {
    const observations = []
    const unsubscribe = subscribeReducedMotion(() => observations.push(reducedMotionSnapshot()))
    assert.equal(reducedMotionSnapshot(), false)
    media.matches = true
    for (const listener of listeners) listener()
    media.matches = false
    for (const listener of listeners) listener()
    assert.deepEqual(observations, [true, false])
    unsubscribe()
    assert.equal(listeners.size, 0)
  } finally {
    if (previousWindow === undefined) delete globalThis.window
    else globalThis.window = previousWindow
  }
})

test('CSS timing tokens convert to Motion easing without an unsupported CSS easing string', () => {
  assert.deepEqual(motionCurve(' cubic-bezier(.16, 1, .3, 1) '), [.16, 1, .3, 1])
  assert.equal(motionCurve('cubic-bezier(1, bad, 1, 1)'), 'linear')
  assert.equal(motionCurve(undefined), 'linear')
})

test('workflow direction follows actual steps including multi-step back and leaves scope pages neutral', () => {
  assert.equal(pageDirection('upload', 'functions'), 1)
  assert.equal(pageDirection('report', 'change'), -1)
  assert.equal(pageDirection('report', 'upload'), -1)
  assert.equal(pageDirection('upload', 'upload'), 0)
  assert.equal(pageDirection('planned', 'report'), 0)
})

test('an unchanged project permits only the immediately previous page to exit', () => {
  const state = createInitialState()
  assert.equal(discardExit(state, state, 0, 1, false), false)
  assert.equal(discardExit(state, state, 0, 2, false), true)
})

test('selecting a new ZIP immediately discards an old report during page exit', () => {
  const state = { ...createInitialState(), report: { old: true } }
  const replaced = workflowReducer(state, { type: 'FILE_SELECTED', file: new File(['zip'], 'new.zip') })
  assert.equal(discardExit(state, replaced, 0, 1, false), true)
})

test('parameter and Symbol edits cannot keep obsolete outgoing evidence alive', () => {
  const state = { ...createInitialState(), report: { old: true } }
  for (const action of [{ type: 'CHANGE_UPDATED', change: { parameterName: 'zone' } }, { type: 'SYMBOL_SELECTED', id: 'page.page' }]) {
    assert.equal(discardExit(state, workflowReducer(state, action), 0, 1, false), true)
  }
})

test('replacing an Analyze/Inspect response invalidates an exit even without a revision change', () => {
  const state = createInitialState()
  assert.equal(discardExit(state, { ...state, report: {} }, 0, 1, false), true)
  assert.equal(discardExit(state, { ...state, inspect: {} }, 0, 1, false), true)
})

test('reduced motion removes exiting content immediately without a deferred animation', () => {
  const state = createInitialState()
  assert.equal(discardExit(state, state, 0, 1, true), true)
})
