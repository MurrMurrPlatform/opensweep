// WebSocket client for /runs/{uid}/ws — the live run transport.
//
// The server tails the run's transcript: on connect it replays events with
// seq > after_seq, then pushes every new event as the run produces it — no
// matter which server process executes the turn. Turns sent on this socket
// additionally stream token deltas.
//
// Server protocol:
//   on connect  → {"type":"status","status":<RunStatus>}
//                 {"type":"event","event":<RunTranscriptEvent>} ×N (replay + live)
//   we send     → {"type":"message","text":"..."} | {"type":"interrupt"}
//   stream back → {"type":"status","status":"running"}
//                 {"type":"delta","text":"..."} ×N
//                 optional {"type":"error","detail":"..."}
//                 {"type":"message_complete","content":"..."}
//                 {"type":"status","status":"awaiting_input"|…}
//
// Disconnecting mid-turn interrupts the turn server-side, so we only
// auto-reconnect on unexpected closes (×3, exponential backoff). Once the
// retries are exhausted the socket is 'unavailable' and the caller should
// fall back to the blocking REST endpoint.
//
// Exception: close codes 4401 (unauthenticated) / 4404 (run not found) are
// terminal — retrying (or falling back to REST, which would fail the same
// way) is pointless, so the socket goes 'unauthorized' and stays there.

import { getCurrentInstance, onUnmounted, ref } from 'vue'
import { wsUrl } from '@/services/api'
import type { RunStatus, RunTranscriptEvent } from '@/types/api'

export type RunSocketState =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'unavailable'
  | 'unauthorized'

/** Terminal server close codes: 4401 unauthenticated, 4404 not found. */
const TERMINAL_CLOSE_CODES = new Set([4401, 4404])

interface ServerFrame {
  type: 'status' | 'delta' | 'event' | 'error' | 'message_complete'
  status?: RunStatus
  text?: string
  event?: RunTranscriptEvent
  detail?: string
  content?: string
}

export interface UseRunSocketOptions {
  /** Last transcript seq already held — the server replays everything after
   *  it. Read on every (re)connect, so return the current value. */
  afterSeq?: () => number
  onStatus?: (status: RunStatus) => void
  onDelta?: (text: string) => void
  /** Structured transcript event (replay + live), always carries a seq. */
  onEvent?: (event: RunTranscriptEvent) => void
  onMessageComplete?: (content: string) => void
  onError?: (detail: string) => void
  /** All reconnect attempts failed — REST fallback territory. */
  onUnavailable?: () => void
  /** Server closed with 4401/4404 — terminal, no reconnect, no REST fallback. */
  onUnauthorized?: (code: number) => void
}

const MAX_RETRIES = 3
const BASE_BACKOFF_MS = 1000

export function useRunSocket(runUid: string, options: UseRunSocketOptions = {}) {
  const state = ref<RunSocketState>('idle')
  let ws: WebSocket | null = null
  let attempts = 0
  let intentionalClose = false
  let retryTimer: ReturnType<typeof setTimeout> | null = null

  function socketUrl(): string {
    // wsUrl appends ?auth_token= when the operator has set one (WS clients
    // cannot send the X-OpenSweep-Auth header).
    const base = wsUrl(`/runs/${runUid}/ws`)
    const seq = Math.max(0, Math.floor(options.afterSeq?.() ?? 0))
    if (!seq) return base
    return `${base}${base.includes('?') ? '&' : '?'}after_seq=${seq}`
  }

  function clearRetry() {
    if (retryTimer !== null) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
  }

  function handleFrame(raw: string) {
    let frame: ServerFrame
    try {
      frame = JSON.parse(raw) as ServerFrame
    } catch {
      return // ignore malformed frames
    }
    switch (frame.type) {
      case 'status':
        if (frame.status) options.onStatus?.(frame.status)
        break
      case 'delta':
        if (typeof frame.text === 'string') options.onDelta?.(frame.text)
        break
      case 'event':
        if (frame.event && typeof frame.event === 'object') options.onEvent?.(frame.event)
        break
      case 'error':
        options.onError?.(frame.detail || 'Unknown run error')
        break
      case 'message_complete':
        options.onMessageComplete?.(frame.content ?? '')
        break
    }
  }

  function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
    clearRetry()
    intentionalClose = false
    state.value = attempts > 0 ? 'reconnecting' : 'connecting'

    let socket: WebSocket
    try {
      socket = new WebSocket(socketUrl())
    } catch {
      scheduleRetry()
      return
    }
    ws = socket

    socket.onopen = () => {
      if (ws !== socket) return
      attempts = 0
      state.value = 'open'
    }
    socket.onmessage = (e) => {
      if (ws !== socket) return
      if (typeof e.data === 'string') handleFrame(e.data)
    }
    socket.onclose = (e) => {
      if (ws !== socket) return
      ws = null
      if (intentionalClose) {
        state.value = 'idle'
        return
      }
      if (TERMINAL_CLOSE_CODES.has(e.code)) {
        // Auth rejection / missing run — retrying can't succeed.
        clearRetry()
        state.value = 'unauthorized'
        options.onUnauthorized?.(e.code)
        return
      }
      scheduleRetry()
    }
    // onerror is always followed by onclose — the retry path lives there.
  }

  function scheduleRetry() {
    if (attempts >= MAX_RETRIES) {
      state.value = 'unavailable'
      options.onUnavailable?.()
      return
    }
    attempts += 1
    state.value = 'reconnecting'
    retryTimer = setTimeout(connect, BASE_BACKOFF_MS * 2 ** (attempts - 1))
  }

  /** Send a follow-up message. Returns false when the socket isn't open (use REST). */
  function send(text: string): boolean {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'message', text }))
      return true
    }
    return false
  }

  /** Interrupt the in-flight turn. Returns false when the socket isn't open. */
  function sendInterrupt(): boolean {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'interrupt' }))
      return true
    }
    return false
  }

  /** Deliberate shutdown — no reconnect. Mid-turn this interrupts the turn. */
  function close() {
    intentionalClose = true
    clearRetry()
    ws?.close()
    ws = null
    state.value = 'idle'
  }

  /** Reset the retry budget and try again (e.g. user-initiated retry). */
  function reconnect() {
    close()
    attempts = 0
    connect()
  }

  if (getCurrentInstance()) {
    onUnmounted(close)
  }

  return { state, connect, reconnect, send, sendInterrupt, close }
}
