<script setup lang="ts">
import { Badge, type BadgeVariants } from '@/components/ui/badge'
import { TableCell, TableRow } from '@/components/ui/table'
import { formatRelativeTime } from '@/lib/utils'
import type { AuditEvent } from '@/types/api'

defineProps<{ event: AuditEvent }>()

const SUBJECT_TONE: Record<string, BadgeVariants['variant']> = {
  Checked: 'info',
  Finding: 'secondary',
  Run: 'warn',
  Sandbox: 'outline',
  Doc: 'success',
  DocEdit: 'success',
  Memory: 'success',
  PolicyVersion: 'warn',
  HumanReview: 'success',
}
</script>

<template>
  <TableRow>
    <TableCell class="whitespace-nowrap font-mono text-xs text-muted-foreground">
      {{ event.occurred_at.slice(11, 19) }}
    </TableCell>
    <TableCell>
      <Badge :variant="SUBJECT_TONE[event.subject_type || ''] || 'secondary'">
        {{ event.subject_type || '—' }}
      </Badge>
    </TableCell>
    <TableCell class="min-w-0">
      <div class="text-sm font-medium">{{ event.kind }}</div>
      <div v-if="event.subject_uid" class="truncate font-mono text-xs text-muted-foreground">
        {{ event.subject_uid }}
      </div>
    </TableCell>
    <TableCell class="whitespace-nowrap text-right text-xs text-muted-foreground">
      {{ formatRelativeTime(event.occurred_at) }}
    </TableCell>
  </TableRow>
</template>
