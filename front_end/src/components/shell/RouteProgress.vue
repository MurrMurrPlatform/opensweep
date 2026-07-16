<script setup lang="ts">
// Slim primary-colored progress bar across the top of the content panel
// during route navigation. Only appears when a navigation takes longer than
// SHOW_DELAY_MS, so instant transitions stay clean; trickles toward 85% and
// snaps to 100% + fades on completion.
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const SHOW_DELAY_MS = 120
const TRICKLE_MS = 200

const router = useRouter()
const visible = ref(false)
const progress = ref(0)

let showTimer: ReturnType<typeof setTimeout> | null = null
let trickleTimer: ReturnType<typeof setInterval> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null

function clearTimers() {
  if (showTimer) clearTimeout(showTimer)
  if (trickleTimer) clearInterval(trickleTimer)
  if (hideTimer) clearTimeout(hideTimer)
  showTimer = trickleTimer = hideTimer = null
}

function start() {
  clearTimers()
  showTimer = setTimeout(() => {
    visible.value = true
    progress.value = 12
    trickleTimer = setInterval(() => {
      // Asymptotic trickle: always advances, never reaches the end.
      progress.value += (85 - progress.value) * 0.18
    }, TRICKLE_MS)
  }, SHOW_DELAY_MS)
}

function finish() {
  const wasVisible = visible.value
  clearTimers()
  if (!wasVisible) return
  progress.value = 100
  hideTimer = setTimeout(() => {
    visible.value = false
    progress.value = 0
  }, 250)
}

let removeGuards: Array<() => void> = []

onMounted(() => {
  removeGuards = [
    router.beforeEach(() => { start() }),
    router.afterEach(() => { finish() }),
    router.onError(() => { finish() }),
  ]
})

onBeforeUnmount(() => {
  clearTimers()
  removeGuards.forEach(remove => remove())
})
</script>

<template>
  <div class="pointer-events-none absolute inset-x-0 top-0 z-50 h-0.5" aria-hidden="true">
    <div
      class="h-full rounded-r-full bg-primary shadow-[0_0_8px_hsl(var(--primary)/0.6)] transition-[width,opacity] duration-200 ease-out"
      :style="{ width: `${progress}%`, opacity: visible ? 1 : 0 }"
    />
  </div>
</template>
