const steps = ['upload', 'functions', 'change', 'report']

export function motionCurve(value) {
  const coordinates = value?.match(/cubic-bezier\(([^)]+)\)/)?.[1].split(',').map(Number)
  return coordinates?.length === 4 && coordinates.every(Number.isFinite) ? coordinates : 'linear'
}

export function pageDirection(from, to) {
  const previous = steps.indexOf(from)
  const next = steps.indexOf(to)
  return previous < 0 || next < 0 || previous === next ? 0 : Math.sign(next - previous)
}

// Presentation lifecycle only. No old project/configuration may remain visible
// while exiting. Rapid navigation retains at most the immediately previous page.
export function discardExit(snapshot, current, mountedSequence, latestSequence, reduced) {
  return reduced || latestSequence > mountedSequence + 1
    || snapshot.revision !== current.revision
    || snapshot.inspect !== current.inspect || snapshot.report !== current.report
}
