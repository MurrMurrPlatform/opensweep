<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { MessagesSquare } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

/**
 * Low-key "discussion open" chip for chat runs linked to a subject. Unlike
 * ActiveRunChip it signals a conversation, not work — it never replaces or
 * gates dispatch buttons, it just links back into the chat.
 */
interface Props {
  run: { uid: string; title: string }
  class?: string
}
const props = defineProps<Props>()

const label = computed(() => {
  const name = (props.run.title || 'Discussion').trim()
  return name.length > 40 ? `${name.slice(0, 40)}…` : name
})
</script>

<template>
  <RouterLink
    :to="{ name: 'run-detail', params: { uid: run.uid } }"
    :class="cn(
      'inline-flex h-8 max-w-full items-center gap-1.5 rounded-full border',
      'bg-muted px-3 text-xs font-medium text-muted-foreground hover:bg-accent transition-colors',
      props.class,
    )"
    :title="`${label} — open the discussion`"
  >
    <MessagesSquare class="h-3.5 w-3.5 shrink-0" />
    <span class="truncate">{{ label }}</span>
    <span class="shrink-0 whitespace-nowrap">→</span>
  </RouterLink>
</template>
