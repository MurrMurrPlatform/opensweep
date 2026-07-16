<script setup lang="ts">
import { computed } from 'vue'
import { Badge, type BadgeVariants } from '@/components/ui/badge'
import type { CIState } from '@/types/api'

interface Props {
  state: CIState
}
const props = defineProps<Props>()

const variant = computed<BadgeVariants['variant']>(() => {
  switch (props.state) {
    case 'green':
      return 'success'
    case 'red':
      return 'destructive'
    case 'pending':
      return 'warn'
    default:
      return 'default'
  }
})
</script>

<template>
  <Badge :variant="variant" class="px-1.5 text-[10px]">CI {{ state }}</Badge>
</template>
