<script setup lang="ts">
import { type Component } from 'vue'
import { cn } from '@/lib/utils'

interface Props {
  title: string
  description?: string
  icon?: Component
  class?: string
}
const props = defineProps<Props>()
</script>

<template>
  <div
    :class="cn(
      'flex flex-col items-center justify-center gap-3 px-6 py-12 text-center sm:py-16',
      'rounded-lg border border-dashed bg-card/50',
      props.class,
    )"
  >
    <div v-if="icon" class="grid size-11 place-items-center rounded-full bg-muted">
      <component :is="icon" class="size-5 text-muted-foreground" aria-hidden="true" />
    </div>
    <div class="space-y-1">
      <h2 class="text-base font-semibold">{{ title }}</h2>
      <p v-if="description" class="mx-auto max-w-md text-sm text-muted-foreground">{{ description }}</p>
    </div>
    <div v-if="$slots.default" class="mt-1 flex flex-wrap items-center justify-center gap-2">
      <slot />
    </div>
  </div>
</template>
