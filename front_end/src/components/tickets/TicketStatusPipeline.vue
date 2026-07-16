<script setup lang="ts">
import { computed } from 'vue'
import { Check } from 'lucide-vue-next'
import { STATUS_LABELS, STATUS_ORDER } from '@/components/tickets/ticketMeta'
import type { TicketStatus } from '@/types/api'

interface Props {
  status: TicketStatus
}
const props = defineProps<Props>()

const currentIdx = computed(() => STATUS_ORDER.indexOf(props.status))

const steps = computed(() =>
  STATUS_ORDER.map((status, idx) => ({
    status,
    label: STATUS_LABELS[status],
    state: idx < currentIdx.value ? ('past' as const) : idx === currentIdx.value ? ('current' as const) : ('future' as const),
  })),
)
</script>

<template>
  <ol class="space-y-0.5">
    <li v-for="(step, idx) in steps" :key="step.status" class="flex items-start gap-2.5">
      <div class="flex flex-col items-center self-stretch">
        <span
          class="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border text-[9px]"
          :class="{
            'border-good bg-good/10 text-good': step.state === 'past' || (step.state === 'current' && step.status === 'done'),
            'border-primary bg-primary text-primary-foreground': step.state === 'current' && step.status !== 'done',
            'border-border text-muted-foreground': step.state === 'future',
          }"
        >
          <Check v-if="step.state === 'past' || (step.state === 'current' && step.status === 'done')" class="h-2.5 w-2.5" />
          <span v-else>{{ idx + 1 }}</span>
        </span>
        <span
          v-if="idx < steps.length - 1"
          class="w-px flex-1 min-h-2"
          :class="step.state === 'past' ? 'bg-good/50' : 'bg-border'"
        />
      </div>
      <div class="pb-2 min-w-0">
        <div
          class="text-sm leading-5"
          :class="step.state === 'current' ? 'font-semibold text-foreground' : step.state === 'past' ? 'text-foreground' : 'text-muted-foreground'"
        >
          {{ step.label }}
        </div>
        <div v-if="step.status === 'todo'" class="text-[10px] text-muted-foreground">Gate 1 — human approval</div>
      </div>
    </li>
  </ol>
</template>
