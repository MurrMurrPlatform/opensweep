// Presentation helpers for Run statuses — notably the quota-paused state,
// which carries retry info in usage.quota.

import type { RunDTO, RunQuotaUsage, RunStatus } from '@/types/api'

type RunLike = Pick<RunDTO, 'status' | 'usage'>

/** Statuses that keep producing output — poll while one of these holds. */
export const LIVE_RUN_STATUSES: RunStatus[] = ['queued', 'running', 'paused_quota']

/** Statuses from which a follow-up message is accepted (V3 §2) — replying to
 *  a failed run is the recovery loop; replying to an ended run reopens it. */
export const FOLLOW_UP_STATUSES: RunStatus[] = [
  'awaiting_input',
  'ended',
  'failed',
  'cancelled',
  'limit_exceeded',
]

export function isLiveRunStatus(status: RunStatus): boolean {
  return LIVE_RUN_STATUSES.includes(status)
}

export function acceptsFollowUp(status: RunStatus): boolean {
  return FOLLOW_UP_STATUSES.includes(status)
}

export function runQuota(run: RunLike): RunQuotaUsage | null {
  const usage = run.usage
  if (!usage || typeof usage !== 'object') return null
  const quota = (usage as Record<string, unknown>).quota
  if (!quota || typeof quota !== 'object' || Array.isArray(quota)) return null
  return quota as RunQuotaUsage
}

function formatEta(iso: string): string {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return iso
  const deltaMin = Math.round((t - Date.now()) / 60_000)
  if (deltaMin > 0 && deltaMin < 120) return `in ~${deltaMin}m`
  return `~${new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
}

/** "Paused (quota) — retry 2 in ~14m" for paused_quota runs, a readable label otherwise. */
export function runStatusLabel(run: RunLike): string {
  if (run.status === 'awaiting_input') return 'awaiting input'
  if (run.status !== 'paused_quota') return run.status
  const quota = runQuota(run)
  const retry = Number(quota?.retry_count ?? 0) + 1
  const eta = typeof quota?.next_retry_at === 'string' && quota.next_retry_at
    ? ` ${formatEta(quota.next_retry_at)}`
    : ''
  return `Paused (quota) — retry ${retry}${eta}`
}

/** Badge variant per status: awaiting_input green, ended neutral,
 *  queued/running live, failures red, paused_quota purple-ish warn. */
export function runStatusVariant(
  status: RunStatus,
): 'success' | 'danger' | 'warn' | 'info' | 'default' {
  if (status === 'awaiting_input') return 'success'
  if (status === 'running' || status === 'queued') return 'info'
  if (status === 'failed' || status === 'cancelled' || status === 'limit_exceeded') return 'danger'
  if (status === 'paused_quota') return 'warn'
  return 'default' // ended
}
