import type { Ref } from 'vue'
import { onBeforeUnmount, ref, watch } from 'vue'

/**
 * Animated number: eases the displayed value toward the source with an
 * ease-out cubic over `durationMs`. Jumps instantly for users who prefer
 * reduced motion. Integers stay integers (rounded per frame).
 */
export function useCountUp(source: Ref<number>, durationMs = 700): Ref<number> {
  // Start at 0 so the first render counts up to the initial value too.
  const display = ref(0)
  let raf = 0

  const reducedMotion = typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  watch(source, (target) => {
    cancelAnimationFrame(raf)
    if (reducedMotion || !Number.isFinite(target)) {
      display.value = target
      return
    }
    const from = display.value
    const start = performance.now()
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs)
      const eased = 1 - Math.pow(1 - t, 3)
      display.value = Math.round(from + (target - from) * eased)
      if (t < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
  }, { immediate: true })

  onBeforeUnmount(() => cancelAnimationFrame(raf))

  return display
}
