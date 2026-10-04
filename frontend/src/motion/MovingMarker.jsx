import { useLayoutEffect, useRef } from 'react'

// One persistent, non-interactive marker. Retarget from its current visual
// position, cancel the earlier animation, and never enqueue another transition.
export default function MovingMarker({ containerRef, selector, identity, className = '' }) {
  const markerRef = useRef(null)
  const initialized = useRef(false)
  const lastVisual = useRef(null)
  useLayoutEffect(() => {
    const container = containerRef.current
    const marker = markerRef.current
    if (!container || !marker) return
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    let animation
    function place(animate = false) {
      const target = container.querySelector(selector)
      if (!target || !target.getClientRects().length) {
        marker.hidden = true
        initialized.current = false
        animation?.cancel()
        return
      }
      const parent = container.getBoundingClientRect()
      const previous = animate && lastVisual.current ? lastVisual.current : marker.getBoundingClientRect()
      lastVisual.current = null
      const next = target.getBoundingClientRect()
      const x = next.left - parent.left + container.scrollLeft - container.clientLeft
      const y = next.top - parent.top + container.scrollTop - container.clientTop
      const end = `translate(${x}px, ${y}px)`
      const oldX = previous.left - parent.left + container.scrollLeft - container.clientLeft
      const oldY = previous.top - parent.top + container.scrollTop - container.clientTop
      animation?.cancel()
      marker.hidden = false
      Object.assign(marker.style, { width: `${next.width}px`, height: `${next.height}px`, transform: end })
      const tokens = getComputedStyle(marker)
      const duration = parseFloat(tokens.getPropertyValue('--oi-motion-feedback')) || 0
      if (animate && initialized.current && !preference.matches && marker.animate && duration) {
        animation = marker.animate([
          { transform: `translate(${oldX}px, ${oldY}px) scale(${previous.width / next.width}, ${previous.height / next.height})` },
          { transform: end },
        ], { duration, easing: tokens.getPropertyValue('--oi-ease-arrive').trim() })
      }
      initialized.current = true
    }
    place(true)
    let initialResize = true
    const resize = new ResizeObserver(() => {
      // Observing an element schedules an initial notification; do not cancel
      // the just-started selection motion with that unchanged measurement.
      if (initialResize) { initialResize = false; return }
      place()
    })
    resize.observe(container)
    const changed = () => place()
    preference.addEventListener('change', changed)
    return () => {
      lastVisual.current = marker.getBoundingClientRect()
      animation?.cancel()
      resize.disconnect()
      preference.removeEventListener('change', changed)
    }
  }, [containerRef, selector, identity])
  return <span ref={markerRef} className={`oi-moving-marker ${className}`} aria-hidden="true" />
}
