<script setup lang="ts">
import { cn } from '@/lib/utils'

interface Props {
  title: string
  subtitle?: string
  class?: string
}
const props = defineProps<Props>()
</script>

<template>
  <header
    :class="cn(
      'mb-4 flex flex-col gap-3 sm:mb-6 sm:flex-row sm:items-end sm:justify-between sm:gap-4',
      props.class,
    )"
  >
    <div class="min-w-0">
      <slot name="breadcrumb" />
      <h1 class="truncate text-xl font-semibold tracking-tight sm:text-2xl">{{ title }}</h1>
      <p v-if="subtitle" class="mt-0.5 text-sm text-muted-foreground">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.default" class="flex shrink-0 flex-wrap items-center gap-2">
      <slot />
    </div>
  </header>
</template>
