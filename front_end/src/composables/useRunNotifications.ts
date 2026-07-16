// Platform-wide run notifications: poll GET /runs/active (org-wide — no
// filters) and toast + chime when a run finishes, fails, or pauses on quota,
// no matter which page is open. Module singleton: ShellLayout starts it once.

import { useRunStore } from '@/stores/runStore'
import { useToast, type ToastAction } from '@/composables/useToast'
import { playError, playInfo, playSuccess } from '@/lib/notifySound'
import type { ActiveRunDTO, RunStatus } from '@/types/api'

const POLL_MS = 6000

let timer: number | undefined
let started = false
let seeded = false
let polling = false
/** Last-seen active runs by uid. */
const prev = new Map<string, ActiveRunDTO>()
/** Uids already warned for the current paused_quota spell. */
const quotaWarned = new Set<string>()

function readableStatus(status: RunStatus): string {
  switch (status) {
    case 'awaiting_input':
    case 'ended':
      return 'finished'
    case 'failed':
      return 'failed'
    case 'limit_exceeded':
      return 'hit its limit'
    case 'cancelled':
      return 'cancelled'
    default:
      return status
  }
}

function runTitle(uid: string, title: string): string {
  return title || `Run ${uid.slice(0, 8)}`
}

function viewAction(uid: string): ToastAction {
  return { label: 'View run', to: { name: 'run-detail', params: { uid } } }
}

async function poll(): Promise<void> {
  if (polling) return
  polling = true
  try {
    const runs = useRunStore()
    const toast = useToast()
    const active = await runs.fetchActive({})
    const current = new Map(active.map((r) => [r.run_uid, r]))

    if (!seeded) {
      // First successful poll only seeds — no toasts for runs already in flight.
      seeded = true
      prev.clear()
      for (const [uid, r] of current) prev.set(uid, r)
      return
    }

    // Runs that left the active set → resolve their final state.
    for (const [uid, last] of prev) {
      if (current.has(uid)) continue
      try {
        const run = await runs.get(uid)
        const title = runTitle(uid, run.title || last.title)
        const message = `${run.playbook || last.playbook} · ${readableStatus(run.status)}`
        const isChat = (run.playbook || last.playbook) === 'chat'
        if (run.status === 'awaiting_input' || run.status === 'ended') {
          if (!isChat) {
            toast.success(title, message, viewAction(uid))
            playSuccess()
          }
        } else if (run.status === 'failed' || run.status === 'limit_exceeded') {
          toast.error(title, message, viewAction(uid))
          playError()
        } else if (run.status === 'cancelled') {
          if (!isChat) toast.info(title, message, viewAction(uid))
        } else {
          // Still active per detail — a race with the list; keep watching it.
          current.set(uid, last)
        }
      } catch {
        /* detail fetch failed — drop it; nothing sensible to report */
      }
    }

    // Runs that flipped into paused_quota while staying active.
    for (const [uid, r] of current) {
      if (r.status === 'paused_quota') {
        const before = prev.get(uid)
        if (before && before.status !== 'paused_quota' && !quotaWarned.has(uid)) {
          quotaWarned.add(uid)
          useToast().warn(
            runTitle(uid, r.title),
            'Paused on provider quota — resumes automatically',
            viewAction(uid),
          )
          playInfo()
        }
      } else {
        quotaWarned.delete(uid) // left paused_quota — re-arm the warning
      }
    }
    for (const uid of quotaWarned) {
      if (!current.has(uid)) quotaWarned.delete(uid)
    }

    prev.clear()
    for (const [uid, r] of current) prev.set(uid, r)
  } catch {
    /* transient poll error — never break the loop, the next tick retries */
  } finally {
    polling = false
  }
}

function onVisibilityChange(): void {
  if (!document.hidden) void poll()
}

/** Start the org-wide notification loop — idempotent, call from ShellLayout. */
export function startRunNotifications(): void {
  if (started) return
  started = true
  timer = window.setInterval(() => {
    if (!document.hidden) void poll()
  }, POLL_MS)
  document.addEventListener('visibilitychange', onVisibilityChange)
  void poll()
}

/** Stop polling (ShellLayout unmount / HMR). Drops seen-state so a later
 *  restart re-seeds silently instead of toasting everything that finished
 *  while nothing was polling. */
export function stopRunNotifications(): void {
  if (timer !== undefined) {
    window.clearInterval(timer)
    timer = undefined
  }
  document.removeEventListener('visibilitychange', onVisibilityChange)
  started = false
  seeded = false
  prev.clear()
  quotaWarned.clear()
}
