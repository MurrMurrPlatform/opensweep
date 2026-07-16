// Display metadata + the client-side view of the ticket status machine.
// The backend enforces transitions (409 on illegal ones); this mirrors it for the UI.

import type { BadgeVariants } from '@/components/ui/badge'
import type { TicketPriority, TicketStatus } from '@/types/api'

export const STATUS_ORDER: TicketStatus[] = ['backlog', 'todo', 'in-progress', 'in-review', 'done']

export const STATUS_LABELS: Record<TicketStatus, string> = {
  backlog: 'Backlog',
  todo: 'Todo',
  'in-progress': 'In Progress',
  'in-review': 'In Review',
  done: 'Done',
}

export interface TicketTransition {
  to: TicketStatus
  label: string
  /** gate = human Gate 1 (Approve), forward = next step, back = step back. */
  kind: 'gate' | 'forward' | 'back'
}

export const TRANSITIONS: Record<TicketStatus, TicketTransition[]> = {
  backlog: [{ to: 'todo', label: 'Approve', kind: 'gate' }],
  todo: [
    { to: 'in-progress', label: 'Start', kind: 'forward' },
    { to: 'backlog', label: 'Back to backlog', kind: 'back' },
  ],
  'in-progress': [
    { to: 'in-review', label: 'To review', kind: 'forward' },
    { to: 'todo', label: 'Back to todo', kind: 'back' },
    { to: 'backlog', label: 'To backlog', kind: 'back' },
  ],
  'in-review': [
    { to: 'done', label: 'Done', kind: 'forward' },
    { to: 'in-progress', label: 'Back to in progress', kind: 'back' },
    { to: 'backlog', label: 'To backlog', kind: 'back' },
  ],
  done: [],
}

export type BadgeVariant = BadgeVariants['variant']

export function priorityVariant(priority: TicketPriority): BadgeVariant {
  switch (priority) {
    case 'urgent':
      return 'destructive'
    case 'high':
      return 'warn'
    case 'medium':
      return 'info'
    default:
      return 'secondary'
  }
}

export function statusVariant(status: TicketStatus): BadgeVariant {
  switch (status) {
    case 'done':
      return 'success'
    case 'in-review':
      return 'info'
    case 'in-progress':
      return 'default'
    case 'todo':
      return 'warn'
    default:
      return 'secondary'
  }
}
