<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { CheckCircle2 } from 'lucide-vue-next'
import { Badge } from '@/components/ui/badge'
import CiStateBadge from '@/components/delivery/CiStateBadge.vue'
import VerdictBadge from '@/components/delivery/VerdictBadge.vue'
import type { PullRequestDTO } from '@/types/api'

interface Props {
  pr: PullRequestDTO
  repoName?: string
  waiveRequests?: number
  showReasons?: boolean
}
const props = withDefaults(defineProps<Props>(), { waiveRequests: 0, showReasons: false })

const counts = computed(() => props.pr.convergence?.counts ?? null)
const reasons = computed(() => {
  if (!props.showReasons) return []
  const list = [...(props.pr.convergence?.reasons ?? [])]
  // The fix-round bound is spent — automation stops, a human takes over.
  if (props.pr.fix_rounds_exhausted === true) list.push('fix rounds exhausted')
  return list
})
</script>

<template>
  <div class="p-4 space-y-2">
    <div class="flex items-start justify-between gap-2">
      <RouterLink
        :to="{ name: 'pull-request-detail', params: { uid: pr.uid } }"
        class="min-w-0 font-medium text-sm hover:text-primary transition-colors"
      >
        <span class="font-mono text-muted-foreground">#{{ pr.github_number }}</span>
        {{ pr.title || '(untitled)' }}
      </RouterLink>
      <Badge v-if="pr.draft" variant="outline" class="px-1.5 text-[10px]">draft</Badge>
    </div>

    <div class="text-xs text-muted-foreground truncate">
      {{ repoName || pr.repository_uid.slice(0, 8) }}
      <template v-if="pr.author"> · {{ pr.author }}</template>
      <template v-if="pr.head_ref"> · <span class="font-mono">{{ pr.head_ref }} → {{ pr.base_ref }}</span></template>
    </div>

    <div class="flex flex-wrap items-center gap-1.5">
      <Badge v-if="pr.converged" variant="success" class="px-1.5 text-[10px]">
        <CheckCircle2 class="h-3 w-3" /> converged
      </Badge>
      <CiStateBadge :state="pr.ci_state" />
      <VerdictBadge :result="pr.convergence?.verdict_result" :fresh="pr.convergence?.verdict_fresh" />
      <Badge v-if="waiveRequests > 0" variant="warn" class="px-1.5 text-[10px]">
        {{ waiveRequests }} waiver request{{ waiveRequests === 1 ? '' : 's' }}
      </Badge>
    </div>

    <div v-if="counts" class="text-xs text-muted-foreground">
      <span :class="counts.blocking > 0 ? 'text-bad font-medium' : ''">{{ counts.blocking }} blocking</span>
      · {{ counts.deferred }} deferred · {{ counts.waived }} waived · {{ counts.info }} info
    </div>

    <div v-if="reasons.length" class="flex flex-wrap gap-1">
      <Badge v-for="reason in reasons" :key="reason" variant="outline" class="max-w-full px-1.5 text-[10px]">
        <span class="truncate">{{ reason }}</span>
      </Badge>
    </div>
  </div>
</template>
