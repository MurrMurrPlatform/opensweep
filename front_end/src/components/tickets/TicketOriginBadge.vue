<script setup lang="ts">
import { computed } from 'vue'
import { Bot, Search, User } from 'lucide-vue-next'
import { Badge } from '@/components/ui/badge'
import type { TicketOrigin } from '@/types/api'

interface Props {
  origin: TicketOrigin
}
const props = defineProps<Props>()

const meta = computed(() => {
  switch (props.origin) {
    case 'finding':
      return { label: 'from finding', variant: 'info' as const, icon: Search }
    case 'agent-proposal':
      return { label: 'agent proposal', variant: 'warn' as const, icon: Bot }
    default:
      return { label: 'human', variant: 'outline' as const, icon: User }
  }
})
</script>

<template>
  <Badge :variant="meta.variant" class="px-1.5 text-[10px]">
    <component :is="meta.icon" class="size-3" /> {{ meta.label }}
  </Badge>
</template>
