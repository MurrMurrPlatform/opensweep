<script setup lang="ts">
import { computed } from 'vue'
import { useCountUp } from '@/composables/useCountUp'

const props = withDefaults(defineProps<{
  value: number
  /** Animation length; keep short — this is feedback, not a show. */
  durationMs?: number
}>(), { durationMs: 700 })

const target = computed(() => props.value)
const display = useCountUp(target, props.durationMs)
</script>

<template>
  <span class="tabular-nums">{{ display.toLocaleString() }}</span>
</template>
