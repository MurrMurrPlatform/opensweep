// Presentation helpers for Campaign statuses and part states — the campaign
// counterpart of lib/runStatus.ts, but already speaking shadcn Badge tones.

import type { BadgeVariants } from '@/components/ui/badge'
import type {
  CampaignDTO,
  CampaignPartState,
  CampaignStatus,
  CampaignTemplate,
} from '@/types/api'

/** Statuses that keep mutating server-side — poll while one of these holds. */
export const LIVE_CAMPAIGN_STATUSES: CampaignStatus[] = ['running', 'finalizing']

export function isLiveCampaignStatus(status: CampaignStatus): boolean {
  return LIVE_CAMPAIGN_STATUSES.includes(status)
}

export function campaignStatusVariant(status: CampaignStatus): BadgeVariants['variant'] {
  if (status === 'running' || status === 'finalizing') return 'info'
  if (status === 'done') return 'success'
  if (status === 'failed' || status === 'cancelled') return 'destructive'
  return 'secondary' // planning
}

export function partStateVariant(state: CampaignPartState): BadgeVariants['variant'] {
  if (state === 'running') return 'info'
  if (state === 'done') return 'success'
  if (state === 'failed') return 'destructive'
  return 'secondary' // pending
}

export const CAMPAIGN_TEMPLATE_LABELS: Record<CampaignTemplate, string> = {
  full: 'Full',
  rotation: 'Rotation',
  focused: 'Focused',
}

/** Finished (done + failed) vs total parts — drives the "3/12 parts" cells. */
export function campaignProgress(c: CampaignDTO): { finished: number; total: number } {
  const parts = c.parts ?? []
  return {
    finished: parts.filter((p) => p.state === 'done' || p.state === 'failed').length,
    total: parts.length,
  }
}
