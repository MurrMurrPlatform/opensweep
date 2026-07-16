<script setup lang="ts">
import { type Component } from 'vue'
import { AlertTriangle } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

interface Props {
  title?: string
  message?: string
  icon?: Component
  class?: string
}
const props = withDefaults(defineProps<Props>(), {
  title: 'Something went wrong',
})
</script>

<template>
  <div
    :class="cn(
      'flex flex-col items-center justify-center gap-3 px-6 py-12 text-center sm:py-16',
      'rounded-lg border border-dashed border-destructive/40 bg-destructive/5',
      props.class,
    )"
    role="alert"
  >
    <div class="grid size-11 place-items-center rounded-full bg-destructive/10">
      <component :is="icon ?? AlertTriangle" class="size-5 text-destructive" aria-hidden="true" />
    </div>
    <div class="space-y-1">
      <h2 class="text-base font-semibold">{{ title }}</h2>
      <p v-if="message" class="mx-auto max-w-md break-words text-sm text-muted-foreground">{{ message }}</p>
    </div>
    <div v-if="$slots.default" class="mt-1 flex flex-wrap items-center justify-center gap-2">
      <slot />
    </div>
  </div>
</template>
