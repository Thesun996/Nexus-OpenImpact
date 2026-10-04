import { useSyncExternalStore } from 'react'

const query = '(prefers-reduced-motion: reduce)'

export function reducedMotionSnapshot() {
  return typeof window !== 'undefined' && window.matchMedia(query).matches
}

export function subscribeReducedMotion(notify) {
  const preference = window.matchMedia(query)
  preference.addEventListener('change', notify)
  return () => preference.removeEventListener('change', notify)
}

// Motion 14's hook reads the initial preference. Subscribe explicitly so an
// accessibility setting changed while this workbench is open takes effect too.
export function useReducedMotionPreference() {
  return useSyncExternalStore(subscribeReducedMotion, reducedMotionSnapshot, () => false)
}
