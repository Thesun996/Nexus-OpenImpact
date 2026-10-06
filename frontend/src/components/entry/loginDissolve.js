// Animate this view only; the workbench mounts after its exit has finished.
export function startLoginDissolve(element, onComplete, style = getComputedStyle(element)) {
  const exit = element.animate([
    { opacity: 1, maskPosition: '100% 0%' },
    { opacity: 1, maskPosition: '50% 0%', offset: .5 },
    { opacity: 0, maskPosition: '0% 0%' },
  ], {
    duration: parseFloat(style.getPropertyValue('--oi-motion-entry-exit')) || 380,
    easing: 'cubic-bezier(.4, 0, .6, 1)',
    fill: 'forwards',
  })
  let active = true
  exit.onfinish = () => {
    if (!active) return
    active = false
    onComplete()
  }
  return () => { active = false; exit.cancel() }
}
