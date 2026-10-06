import anime from 'animejs'

// One scoped timeline; cancellation also guards callbacks during StrictMode replay.
export function startBrandReveal(characters, onComplete, animation = anime) {
  let cancelled = false
  const timeline = animation.timeline({ autoplay: false, loop: false,
    complete: () => { if (!cancelled) onComplete() } })
  timeline.add({ targets: characters, opacity: [0, 1], translateY: [12, 0],
    duration: 420, delay: animation.stagger(65), easing: 'easeOutQuad' })
  timeline.add({ targets: characters, opacity: [1, 0],
    translateY: (_, index) => index % 2 ? -12 : 12,
    translateX: (_, index) => (index - (characters.length - 1) / 2) * 2,
    duration: 340, delay: animation.stagger(12), easing: 'easeInQuad' }, '+=650')
  timeline.play()
  return () => {
    cancelled = true
    timeline.pause()
    animation.remove(characters)
  }
}
