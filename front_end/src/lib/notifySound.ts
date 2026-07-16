// Tiny Web Audio chimes for run notifications — no audio assets, just
// oscillators with soft gain envelopes. Every entry point is wrapped in
// try/catch: sound is a nicety and must never break the app (autoplay
// policies, missing AudioContext, etc.).

import { ref } from 'vue'

const STORAGE_KEY = 'opensweep_notification_sounds'

/** Global mute switch, persisted in localStorage ('on'/'off'). */
export const soundsEnabled = ref<boolean>(readInitialEnabled())

function readInitialEnabled(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== 'off'
  } catch {
    return true
  }
}

export function toggleSounds(): void {
  soundsEnabled.value = !soundsEnabled.value
  try {
    localStorage.setItem(STORAGE_KEY, soundsEnabled.value ? 'on' : 'off')
  } catch {
    /* private mode — the toggle still works for this session */
  }
}

let ctx: AudioContext | null = null

function getContext(): AudioContext | null {
  try {
    if (!ctx) {
      const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctor) return null
      ctx = new Ctor()
    }
    if (ctx.state === 'suspended') void ctx.resume()
    return ctx
  } catch {
    return null
  }
}

/** One sine note with a quick exponential attack/release envelope. */
function playTone(freq: number, startAt: number, dur: number, gainPeak: number): void {
  const audio = getContext()
  if (!audio) return
  try {
    const t0 = audio.currentTime + startAt
    const osc = audio.createOscillator()
    const gain = audio.createGain()
    osc.type = 'sine'
    osc.frequency.setValueAtTime(freq, t0)
    gain.gain.setValueAtTime(0.0001, t0)
    gain.gain.exponentialRampToValueAtTime(gainPeak, t0 + 0.015)
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur)
    osc.connect(gain)
    gain.connect(audio.destination)
    osc.start(t0)
    osc.stop(t0 + dur + 0.05)
  } catch {
    /* never throw from a chime */
  }
}

/** Two gentle ascending notes — a run finished. */
export function playSuccess(): void {
  if (!soundsEnabled.value) return
  markChimePlayed()
  playTone(587.33, 0, 0.16, 0.06) // D5
  playTone(880, 0.09, 0.22, 0.06) // A5
}

/** Two low descending notes — a run failed. */
export function playError(): void {
  if (!soundsEnabled.value) return
  markChimePlayed()
  playTone(440, 0, 0.22, 0.05) // A4
  playTone(233.08, 0.14, 0.3, 0.05) // A#3
}

/** Single soft ping — informational (e.g. paused on quota). */
export function playInfo(): void {
  if (!soundsEnabled.value) return
  markChimePlayed()
  playTone(660, 0, 0.18, 0.045)
}

/* ── Micro UI ticks ─────────────────────────────────────────────────────
   Much quieter and shorter than the run chimes above; used for toast
   feedback. A short refractory window keeps them from stacking on top of a
   melodic run chime (run notifications chime AND toast). */

let lastSoundAt = 0

function tickAllowed(): boolean {
  if (!soundsEnabled.value) return false
  const now = performance.now()
  if (now - lastSoundAt < 500) return false
  lastSoundAt = now
  return true
}

/** Whisper-level confirmation blip — successful action feedback. */
export function playUiSuccess(): void {
  if (!tickAllowed()) return
  playTone(830.6, 0, 0.09, 0.025) // G#5, barely-there
}

/** Whisper-level low blip — an action failed. */
export function playUiError(): void {
  if (!tickAllowed()) return
  playTone(311.13, 0, 0.14, 0.03) // D#4
}

/** Mark that a full chime just played so UI ticks back off briefly. */
export function markChimePlayed(): void {
  lastSoundAt = performance.now()
}
