<script setup lang="ts">
import { Badge, type BadgeVariants } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatRelativeTime } from '@/lib/utils'
import type { Sandbox } from '@/types/api'

defineProps<{ sandbox: Sandbox }>()
defineEmits<{ destroy: [uid: string] }>()

const STATUS_TONE: Record<string, BadgeVariants['variant']> = {
  preparing: 'info',
  ready: 'info',
  running: 'warn',
  completed: 'success',
  failed: 'destructive',
  destroyed: 'outline',
}
</script>

<template>
  <div
    class="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1 rounded-md px-4 py-3 transition-colors hover:bg-accent sm:grid-cols-[auto_1fr_auto_auto_auto]"
  >
    <Badge :variant="STATUS_TONE[sandbox.status]">{{ sandbox.status }}</Badge>
    <div class="col-start-1 col-end-[-1] min-w-0 sm:col-auto">
      <div class="truncate font-mono text-sm">{{ sandbox.host_path }}</div>
      <div class="truncate text-xs text-muted-foreground">
        {{ sandbox.source_branch }} → {{ sandbox.sandbox_branch }}
      </div>
    </div>
    <span class="whitespace-nowrap text-xs text-muted-foreground">created {{ formatRelativeTime(sandbox.created_at) }}</span>
    <span class="whitespace-nowrap text-xs text-muted-foreground">
      cleanup {{ sandbox.cleanup_after ? formatRelativeTime(sandbox.cleanup_after) : '—' }}
    </span>
    <Button
      v-if="sandbox.status !== 'destroyed'"
      size="sm"
      variant="ghost"
      @click="$emit('destroy', sandbox.uid)"
    >Destroy</Button>
  </div>
</template>
