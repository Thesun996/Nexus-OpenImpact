import { useCallback, useLayoutEffect, useRef, useState } from 'react'
import { AnimatePresence, domAnimation, LazyMotion, m, MotionConfig, usePresence, usePresenceData } from 'motion/react'
import { useWorkflow } from '../state/WorkflowContext.jsx'
import { discardExit, motionCurve } from './pageTransition.js'
import { useReducedMotionPreference } from './reducedMotion.js'

function MotionPage({ children, sequence, direction, measure, finish }) {
  const pageRef = useRef(null)
  const { state } = useWorkflow()
  const [present, safeToRemove] = usePresence()
  const reduced = useReducedMotionPreference()
  const latest = usePresenceData()
  const snapshot = useRef(state)
  const mountedSequence = useRef(sequence)
  if (present) { snapshot.current = state; mountedSequence.current = sequence }
  const immediate = reduced || latest.skipSequence === latest.sequence
  const discard = !present && (immediate || discardExit(snapshot.current, state, mountedSequence.current, latest.sequence, reduced))
  useLayoutEffect(() => { if (discard) safeToRemove?.() }, [discard, safeToRemove])
  useLayoutEffect(() => {
    const element = pageRef.current
    if (!present || !element) return
    const update = () => measure(element.offsetHeight, sequence)
    update()
    const resize = new ResizeObserver(update)
    resize.observe(element)
    return () => resize.disconnect()
  }, [present, sequence, measure])
  // CSS owns all durations and travel, including the smaller mobile distance.
  const tokens = typeof window === 'undefined' ? null : getComputedStyle(document.documentElement)
  const number = (name) => parseFloat(tokens?.getPropertyValue(name)) || 0
  const travel = reduced ? 0 : number('--oi-motion-travel')
  const arrival = motionCurve(tokens?.getPropertyValue('--oi-ease-page'))
  const departure = motionCurve(tokens?.getPropertyValue('--oi-ease-depart'))
  // Keep Motion's exit participant mounted until its zero-duration completion
  // runs. Unmounting it before notifying the presence boundary can deadlock
  // wait mode. Invalid outgoing content is hidden immediately, never reused.
  return <m.div ref={pageRef} className="oi-motion-page" data-page-active={present}
    inert={!present} aria-hidden={!present || undefined}
    style={{ visibility: discard ? 'hidden' : undefined }}
    initial={immediate || !direction ? false : { opacity: 0, y: direction * travel }}
    animate={{ opacity: 1, y: 0, transition: { duration: immediate ? 0 : number('--oi-motion-enter') / 1000, ease: arrival } }}
    exit={{ opacity: 0, transition: { duration: immediate || discard ? 0 : number('--oi-motion-exit') / 1000, ease: departure } }}
    onAnimationComplete={(definition) => {
      if (present && definition.opacity === 1) finish(sequence)
      // usePresence registers a manual participant as well as the motion div.
      // Complete both participants; otherwise wait mode would remain on an
      // invisible exiting page even after its fade has finished.
      else if (!present && definition.opacity === 0) safeToRemove?.()
    }}>
    {children}
  </m.div>
}

export default function WorkflowPages({ page, direction, sequence, children }) {
  const reduced = useReducedMotionPreference()
  const stackRef = useRef(null)
  const height = useRef(0)
  const pendingTab = useRef(null)
  const [skipSequence, setSkipSequence] = useState(-1)
  const currentSequence = useRef(sequence)
  currentSequence.current = sequence
  const measure = useCallback((value, measuredSequence) => {
    if (measuredSequence !== currentSequence.current) return
    height.current = value
    if (pendingTab.current === measuredSequence) {
      pendingTab.current = null
      const stack = stackRef.current
      const first = [...stack.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex="0"]')]
        .find((element) => !element.closest('[inert]') && element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden')
      first?.focus({ preventScroll: true })
      stack.style.minHeight = ''
    }
  }, [])
  const finish = useCallback((finishedSequence) => {
    // An interrupted entry must not release the next transition's reservation.
    if (finishedSequence === currentSequence.current && stackRef.current) stackRef.current.style.minHeight = ''
  }, [])
  useLayoutEffect(() => {
    const main = document.getElementById('oi-main')
    const tabDuringExit = (event) => {
      if (event.key !== 'Tab' || event.shiftKey || document.activeElement !== main
        || !stackRef.current?.querySelector('[data-page-active="false"]')) return
      // Fulfil Tab on the incoming page instead of cycling out of an inert old
      // page. Only this transition is cut short; Shift+Tab remains native.
      event.preventDefault()
      pendingTab.current = currentSequence.current
      setSkipSequence(currentSequence.current)
    }
    main.addEventListener('keydown', tabDuringExit)
    return () => main.removeEventListener('keydown', tabDuringExit)
  }, [])
  useLayoutEffect(() => {
    if (pendingTab.current !== sequence) pendingTab.current = null
    const stack = stackRef.current
    // Keep the old page's measured space throughout exit + entry. The entering
    // page may naturally grow; no absolute layers or animated heights are used.
    if (stack) stack.style.minHeight = !reduced && sequence ? `${height.current}px` : ''
    window.scrollTo({ top: 0 })
    document.getElementById('oi-main')?.focus({ preventScroll: true })
  }, [page, reduced])
  return <LazyMotion features={domAnimation}><MotionConfig reducedMotion={reduced ? 'always' : 'never'}>
    <div ref={stackRef} className="oi-page-stack"><AnimatePresence initial={false} mode="wait" custom={{ sequence, skipSequence }}>
      <MotionPage key={page} sequence={sequence} direction={direction} measure={measure} finish={finish}>{children}</MotionPage>
    </AnimatePresence></div>
  </MotionConfig></LazyMotion>
}
