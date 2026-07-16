<script setup lang="ts">
import { computed } from 'vue'
import { Badge, type BadgeVariants } from '@/components/ui/badge'
import VerdictBadge from '@/components/delivery/VerdictBadge.vue'
import type { VerdictDTO } from '@/types/api'

interface Props {
  verdict: VerdictDTO
  headSha: string
}
const props = defineProps<Props>()

const fresh = computed(() => Boolean(props.headSha) && props.verdict.sha === props.headSha)

function acVariant(result: string): BadgeVariants['variant'] {
  if (result === 'pass') return 'success'
  if (result === 'fail') return 'destructive'
  return 'default'
}

/** Skeptic pass (§A): pending = a verification run is challenging the
 *  findings; adjusted = this verdict was produced by it (only survivors
 *  counted); failed = verification never completed, original stands. */
const verification = computed(() => {
  switch (props.verdict.verification_status) {
    case 'pending':
      return { label: 'verification in progress', variant: 'info' as const,
               title: 'A skeptic run is challenging these findings — the verdict may still be adjusted.' }
    case 'adjusted':
      return { label: 'verified — survivors only', variant: 'success' as const,
               title: 'This verdict was adjusted by a verification run: refuted findings were dismissed.' }
    case 'failed':
      return { label: 'verification failed', variant: 'warn' as const,
               title: 'The verification run never completed; all findings count as confirmed.' }
    case 'superseded':
      return { label: 'superseded', variant: 'outline' as const,
               title: 'An adjusted verdict at the same commit replaced this one.' }
    default:
      return null
  }
})
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center gap-2 text-xs">
      <VerdictBadge :result="verdict.result" :fresh="fresh" />
      <span class="font-mono text-muted-foreground">@ {{ verdict.sha.slice(0, 10) }}</span>
      <span class="text-muted-foreground">{{ verdict.executor }}</span>
      <span v-if="verdict.created_at" class="text-muted-foreground">· {{ verdict.created_at }}</span>
      <Badge
        v-if="verdict.new_blocking_findings > 0"
        variant="destructive"
        class="px-1.5 text-[10px]"
      >
        {{ verdict.new_blocking_findings }} new blocking finding{{ verdict.new_blocking_findings === 1 ? '' : 's' }}
      </Badge>
      <Badge v-if="verification" :variant="verification.variant" class="px-1.5 text-[10px]" :title="verification.title">
        {{ verification.label }}
      </Badge>
    </div>

    <div v-if="verdict.ac_results.length" class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-xs text-muted-foreground border-b">
            <th class="py-1.5 pr-3 font-medium">Acceptance criterion</th>
            <th class="py-1.5 pr-3 font-medium">Result</th>
            <th class="py-1.5 font-medium">Note</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border">
          <tr v-for="(ac, idx) in verdict.ac_results" :key="idx">
            <td class="py-2 pr-3 align-top">{{ ac.criterion }}</td>
            <td class="py-2 pr-3 align-top">
              <Badge :variant="acVariant(ac.result)" class="px-1.5 text-[10px]">{{ ac.result }}</Badge>
            </td>
            <td class="py-2 align-top text-muted-foreground text-xs">{{ ac.note || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="text-xs text-muted-foreground">No acceptance criteria recorded on this verdict.</div>
  </div>
</template>
