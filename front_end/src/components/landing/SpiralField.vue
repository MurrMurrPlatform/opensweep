<script setup lang="ts">
// Animated spiral of fine lines with a radar sweep: a glowing beam rotates
// over the slowly turning arms and lights up small blips as it passes —
// OpenSweep sweeping a repo. Draws on a canvas sized to its parent; colors
// derive from the active brand token so it follows the color scheme and the
// light/dark theme.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{ theme: 'light' | 'dark' }>()

const canvas = ref<HTMLCanvasElement | null>(null)
let raf = 0
let ro: ResizeObserver | null = null
let reducedMotion = false
let palette = { h: 235, s: 70, l: 60 }

function hexToHsl(hex: string): { h: number; s: number; l: number } | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return null
  const n = parseInt(m[1], 16)
  const r = ((n >> 16) & 255) / 255
  const g = ((n >> 8) & 255) / 255
  const b = (n & 255) / 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  if (max === min) return { h: 0, s: 0, l: l * 100 }
  const d = max - min
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  let h: number
  if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6
  else if (max === g) h = ((b - r) / d + 2) / 6
  else h = ((r - g) / d + 4) / 6
  return { h: h * 360, s: s * 100, l: l * 100 }
}

function readPalette() {
  const brand = getComputedStyle(document.documentElement).getPropertyValue('--n-brand')
  palette = hexToHsl(brand) ?? palette
}

function resize() {
  const c = canvas.value
  if (!c || !c.parentElement) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const { clientWidth: w, clientHeight: h } = c.parentElement
  c.width = Math.max(1, Math.round(w * dpr))
  c.height = Math.max(1, Math.round(h * dpr))
  c.style.width = `${w}px`
  c.style.height = `${h}px`
  if (reducedMotion) draw(0)
}

function draw(t: number) {
  const c = canvas.value
  if (!c) return
  const ctx = c.getContext('2d')
  if (!ctx) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const w = c.width / dpr
  const h = c.height / dpr
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, h)

  const dark = props.theme === 'dark'
  const cx = w * 0.66
  const cy = h * 0.34
  const maxR = Math.min(w * 0.26, h * 0.38)
  const ARMS = 44
  const TURNS = Math.PI * 2.4
  const STEPS = 88
  ctx.lineWidth = 1.2

  for (let i = 0; i < ARMS; i++) {
    const p = i / (ARMS - 1)
    const base = p * Math.PI * 2 + t * 0.00006
    const wob = Math.sin(t * 0.00024 + p * Math.PI * 4)
    const hue = palette.h - 26 + p * 52
    const alpha = 0.09 + 0.26 * p
    const light = dark ? 58 + p * 20 : 40 + p * 16
    ctx.strokeStyle = `hsla(${hue}, ${dark ? 74 : 62}%, ${light}%, ${alpha})`
    ctx.beginPath()
    for (let s = 0; s <= STEPS; s++) {
      const q = s / STEPS
      const theta = base + q * TURNS + wob * 0.12 * Math.sin(q * Math.PI * 2)
      // Small inner hole so the arms don't pile into a bright knot at center.
      const r = maxR * (0.06 + 0.94 * Math.pow(q, 0.72))
      const x = cx + Math.cos(theta) * r
      const y = cy + Math.sin(theta) * r * 0.8
      if (s === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    }
    ctx.stroke()
  }

  // ── Radar sweep: beam + trail + blips, in the squashed (elliptical) space ──
  const TAU = Math.PI * 2
  const beam = t * 0.0005 // ~12.5s per revolution
  ctx.save()
  ctx.translate(cx, cy)
  ctx.scale(1, 0.8)

  if (typeof ctx.createConicGradient === 'function') {
    const trail = (a: number) =>
      `hsla(${palette.h}, ${dark ? 80 : 66}%, ${dark ? 62 : 52}%, ${a})`
    const g = ctx.createConicGradient(beam, 0, 0)
    g.addColorStop(0, trail(0))
    g.addColorStop(0.6, trail(0))
    g.addColorStop(1, trail(dark ? 0.16 : 0.1))
    ctx.fillStyle = g
    ctx.beginPath()
    ctx.arc(0, 0, maxR, 0, TAU)
    ctx.fill()
  }

  // Leading edge with glow
  ctx.strokeStyle = `hsla(${palette.h}, 85%, ${dark ? 70 : 55}%, 0.65)`
  ctx.shadowColor = `hsla(${palette.h}, 90%, ${dark ? 65 : 55}%, 0.9)`
  ctx.shadowBlur = 16
  ctx.lineWidth = 1.5
  ctx.beginPath()
  ctx.moveTo(Math.cos(beam) * maxR * 0.07, Math.sin(beam) * maxR * 0.07)
  ctx.lineTo(Math.cos(beam) * maxR, Math.sin(beam) * maxR)
  ctx.stroke()
  ctx.shadowBlur = 0

  // Blips flare as the beam passes, then fade until the next revolution
  for (let i = 0; i < 8; i++) {
    const a = (i * 2.399963) % TAU // golden angle: even but organic spread
    const rr = maxR * (0.22 + 0.68 * ((i * 0.381966) % 1))
    let d = (beam - a) % TAU
    if (d < 0) d += TAU
    const glow = Math.exp(-d * 2.4)
    if (glow < 0.02) continue
    const x = Math.cos(a) * rr
    const y = Math.sin(a) * rr
    const fill = `hsla(${palette.h}, 90%, ${dark ? 72 : 50}%, ${0.85 * glow})`
    ctx.fillStyle = fill
    ctx.shadowColor = fill
    ctx.shadowBlur = 14 * glow
    ctx.beginPath()
    ctx.arc(x, y, 2.2 + 2 * glow, 0, TAU)
    ctx.fill()
  }
  ctx.restore()
}

function loop(t: number) {
  draw(t)
  raf = requestAnimationFrame(loop)
}

onMounted(() => {
  reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  readPalette()
  ro = new ResizeObserver(resize)
  if (canvas.value?.parentElement) ro.observe(canvas.value.parentElement)
  resize()
  if (reducedMotion) draw(0)
  else raf = requestAnimationFrame(loop)
})

watch(
  () => props.theme,
  () => {
    readPalette()
    if (reducedMotion) draw(0)
  },
)

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  ro?.disconnect()
})
</script>

<template>
  <canvas ref="canvas" class="pointer-events-none block" aria-hidden="true" />
</template>
