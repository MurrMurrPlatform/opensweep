<script setup lang="ts">
import { computed } from 'vue'
import { CheckCircle2, XCircle } from 'lucide-vue-next'
import type { ConvergenceState } from '@/types/api'

interface Props {
  convergence: ConvergenceState | null
}
const props = defineProps<Props>()

interface Predicate {
  label: string
  pass: boolean
  detail: string
}

/** The four conditions of the convergence predicate (PLATFORM_V2_DESIGN.md §5). */
const predicates = computed<Predicate[]>(() => {
  const c = props.convergence
  if (!c) return []
  const reasons = c.reasons ?? []
  const find = (match: (r: string) => boolean) => reasons.find(match) ?? ''
  return [
    {
      label: 'CI strictly green',
      pass: c.ci_state === 'green',
      detail: find((r) => r.startsWith('ci not green')) || `state=${c.ci_state}`,
    },
    {
      label: 'Verdict fresh @ head + approve',
      pass: c.verdict_fresh && c.verdict_result === 'approve',
      detail:
        find((r) => r.startsWith('no verdict') || r.startsWith('verdict is')) ||
        (c.verdict_sha ? `verdict@${c.verdict_sha.slice(0, 10)}` : ''),
    },
    {
      label: 'Clean round — zero new blocking findings',
      pass: c.clean_round,
      detail: find((r) => r.includes('clean round')),
    },
    {
      label: 'Ledger clear — zero blocking resolutions',
      pass: c.counts.blocking === 0,
      detail: find((r) => r.includes('blocking finding(s) unresolved')),
    },
  ]
})
</script>

<template>
  <div v-if="!convergence" class="text-sm text-muted-foreground">
    No convergence state computed yet — recompute or re-sync this PR.
  </div>
  <ul v-else class="space-y-2.5">
    <li v-for="p in predicates" :key="p.label" class="flex items-start gap-2.5">
      <CheckCircle2 v-if="p.pass" class="h-4 w-4 mt-0.5 shrink-0 text-good" />
      <XCircle v-else class="h-4 w-4 mt-0.5 shrink-0 text-bad" />
      <div class="min-w-0">
        <div class="text-sm font-medium" :class="p.pass ? '' : 'text-foreground'">{{ p.label }}</div>
        <div v-if="p.detail" class="text-xs font-mono" :class="p.pass ? 'text-muted-foreground' : 'text-bad'">
          {{ p.detail }}
        </div>
      </div>
    </li>
  </ul>
</template>
