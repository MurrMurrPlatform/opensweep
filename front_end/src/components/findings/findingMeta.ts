// Display metadata for findings, shared by the list, detail and ledger views.

import type { BadgeVariants } from '@/components/ui/badge'
import type { Severity } from '@/types/api'

export const SEVERITY_RANK: Record<string, number> = { low: 0, medium: 1, high: 2, critical: 3 }

export function severityVariant(sev: Severity): BadgeVariants['variant'] {
  if (sev === 'critical' || sev === 'high') return 'destructive'
  if (sev === 'medium') return 'warn'
  return 'secondary'
}
