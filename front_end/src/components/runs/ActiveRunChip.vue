<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { Loader2 } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import type { ActiveRunDTO } from '@/types/api'

/**
 * Prominent "<title-or-kind> running — view run →" chip shown on dispatch
 * surfaces while a same-target run is in flight. Links to the run detail page.
 */
interface Props {
  run: ActiveRunDTO
  class?: string
}
const props = defineProps<Props>()

const label = computed(() => {
  const name = (props.run.title || props.run.playbook || 'Run').trim()
  return name.length > 48 ? `${name.slice(0, 48)}…` : name
})

const verb = computed(() => {
  if (props.run.status === 'queued') return 'queued'
  if (props.run.status === 'paused_quota') return 'paused'
  return 'running'
})
</script>

<template>
  <RouterLink
    :to="{ name: 'run-detail', params: { uid: run.run_uid } }"
    :class="cn(
      'inline-flex h-8 max-w-full items-center gap-1.5 rounded-full border border-warn/40 bg-warn/10',
      'px-3 text-xs font-medium text-warn hover:bg-warn/20 transition-colors',
      props.class,
    )"
    :title="`${label} · ${verb} — open the run`"
  >
    <Loader2 class="h-3.5 w-3.5 shrink-0 animate-spin" />
    <span class="truncate">{{ label }} {{ verb }}</span>
    <span class="shrink-0 whitespace-nowrap">— view run →</span>
  </RouterLink>
</template>
