<script setup lang="ts">
import { computed } from 'vue'
import { Badge, type BadgeVariants } from '@/components/ui/badge'
import type { VerdictResult } from '@/types/api'

interface Props {
  result?: VerdictResult | null
  fresh?: boolean
}
const props = defineProps<Props>()

const variant = computed<BadgeVariants['variant']>(() => {
  if (!props.result) return 'outline'
  if (!props.fresh) return 'default' // stale verdicts never count
  if (props.result === 'approve') return 'success'
  if (props.result === 'needs_human') return 'warn'
  return 'destructive'
})

const label = computed(() => {
  if (!props.result) return 'no verdict'
  return `${props.result.replace(/_/g, ' ')} · ${props.fresh ? 'fresh' : 'stale'}`
})
</script>

<template>
  <Badge :variant="variant" class="px-1.5 text-[10px]">{{ label }}</Badge>
</template>
