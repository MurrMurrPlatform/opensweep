<script setup lang="ts">
// The implementation checklist (ticket.plan.steps / thread.plan_steps):
// submitted with the plan, marked off by the agent via update_plan_step
// while implementing.
import { CheckCircle2, Circle, CircleDot } from 'lucide-vue-next'
import type { PlanStep } from '@/types/api'

defineProps<{ steps: PlanStep[] }>()
</script>

<template>
  <ol class="space-y-1.5">
    <li v-for="step in steps" :key="step.id" class="flex items-start gap-2 text-sm">
      <CheckCircle2 v-if="step.status === 'done'" class="mt-0.5 size-4 shrink-0 text-good" />
      <CircleDot
        v-else-if="step.status === 'in_progress'"
        class="mt-0.5 size-4 shrink-0 animate-pulse text-primary"
      />
      <Circle v-else class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
      <span :class="step.status === 'done' ? 'text-muted-foreground line-through' : ''">
        {{ step.title }}
        <span v-if="step.notes" class="block text-xs text-muted-foreground">{{ step.notes }}</span>
      </span>
    </li>
  </ol>
</template>
