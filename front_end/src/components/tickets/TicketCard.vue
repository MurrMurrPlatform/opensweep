<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { GitPullRequest, Layers } from 'lucide-vue-next'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { formatRelativeTime } from '@/lib/utils'
import TicketImplementButton from '@/components/tickets/TicketImplementButton.vue'
import TicketOriginBadge from '@/components/tickets/TicketOriginBadge.vue'
import TicketTransitionButtons from '@/components/tickets/TicketTransitionButtons.vue'
import { priorityVariant } from '@/components/tickets/ticketMeta'
import type { TicketDTO } from '@/types/api'

interface Props {
  ticket: TicketDTO
  subticketCount?: number
}
withDefaults(defineProps<Props>(), { subticketCount: 0 })
defineEmits<{ updated: [ticket: TicketDTO]; deleted: [uid: string] }>()
</script>

<template>
  <Card class="space-y-2 p-3 transition-colors hover:border-primary/40">
    <RouterLink
      :to="{ name: 'ticket-detail', params: { uid: ticket.uid } }"
      class="block min-w-0 text-sm font-medium transition-colors hover:text-primary"
    >
      {{ ticket.title || '(untitled)' }}
    </RouterLink>

    <div class="flex flex-wrap items-center gap-1.5">
      <Badge :variant="priorityVariant(ticket.priority)" class="px-1.5 text-[10px]">{{ ticket.priority }}</Badge>
      <Badge v-if="ticket.size" variant="outline" class="px-1.5 text-[10px]">{{ ticket.size }}</Badge>
      <TicketOriginBadge :origin="ticket.origin" />
      <Badge v-if="ticket.linked_pr_uids.length" variant="outline" class="px-1.5 text-[10px]">
        <GitPullRequest class="size-3" /> {{ ticket.linked_pr_uids.length }}
      </Badge>
      <Badge v-if="subticketCount > 0" variant="outline" class="px-1.5 text-[10px]">
        <Layers class="size-3" /> {{ subticketCount }} subticket{{ subticketCount === 1 ? '' : 's' }}
      </Badge>
      <span
        v-if="ticket.created_at"
        class="ml-auto text-[10px] text-muted-foreground"
        :title="`Created ${new Date(ticket.created_at).toLocaleString()}`"
      >{{ formatRelativeTime(ticket.created_at) }}</span>
    </div>

    <div v-if="ticket.labels.length" class="flex flex-wrap gap-1">
      <Badge v-for="label in ticket.labels" :key="label" variant="secondary" class="px-1.5 text-[10px]">{{ label }}</Badge>
    </div>

    <div class="flex flex-wrap items-center gap-1.5 pt-1">
      <TicketImplementButton compact :ticket="ticket" @updated="$emit('updated', $event)" />
      <TicketTransitionButtons
        :ticket="ticket"
        @updated="$emit('updated', $event)"
        @deleted="$emit('deleted', $event)"
      />
    </div>
  </Card>
</template>
