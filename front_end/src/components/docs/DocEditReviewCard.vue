<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { Archive, Check, X } from 'lucide-vue-next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { collapseContext, lineDiff } from '@/lib/lineDiff'
import type { DocEditDTO } from '@/types/api'

const props = defineProps<{
  edit: DocEditDTO
  /** Optional label for the edit's target (page slug / "new page · …"). */
  target?: string
  /** This edit is being resolved right now (spinner on Accept). */
  resolving?: boolean
  /** Another resolution (single or bulk) is in flight — lock the buttons. */
  disabled?: boolean
}>()

defineEmits<{ accept: []; reject: [] }>()

const diff = computed(() => collapseContext(lineDiff(props.edit.current_body || '', props.edit.proposed_body || '')))
</script>

<template>
  <div class="border-b border-border p-4 last:border-b-0 space-y-2">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="min-w-0">
        <div v-if="target" class="flex flex-wrap items-center gap-1.5 text-sm font-medium">
          {{ target }}
          <Badge v-if="!edit.doc_uid" variant="info" class="px-1.5 text-[10px]">new page</Badge>
          <Badge v-if="edit.proposed_archived" variant="destructive" class="px-1.5 text-[10px]">
            <Archive class="h-3 w-3" /> proposes retiring
          </Badge>
        </div>
        <div v-else-if="edit.proposed_archived" class="flex flex-wrap items-center gap-1.5">
          <Badge variant="destructive" class="px-1.5 text-[10px]">
            <Archive class="h-3 w-3" /> proposes retiring
          </Badge>
        </div>
        <div class="text-xs text-muted-foreground">
          <span v-if="edit.source_run_uid">
            {{ target ? 'run' : 'proposed by run' }}
            <RouterLink
              :to="{ name: 'run-detail', params: { uid: edit.source_run_uid } }"
              class="font-mono text-primary hover:underline"
            >{{ edit.source_run_uid.slice(0, 8) }}</RouterLink>
          </span>
          <span v-if="edit.created_at"> · {{ edit.created_at.slice(0, 10) }}</span>
        </div>
      </div>
      <div class="flex gap-2">
        <Button variant="outline" size="sm" :disabled="disabled || resolving" @click="$emit('reject')">
          <X /> Reject
        </Button>
        <Button size="sm" :loading="resolving" :disabled="disabled" @click="$emit('accept')">
          <Check /> Accept
        </Button>
      </div>
    </div>

    <p v-if="edit.rationale" class="text-sm text-muted-foreground">{{ edit.rationale }}</p>

    <div class="overflow-x-auto rounded-md border border-border bg-muted font-mono text-xs leading-5">
      <div
        v-for="(line, i) in diff"
        :key="i"
        :class="[
          'whitespace-pre-wrap break-all px-3',
          line.type === 'add' ? 'bg-green-500/15 text-green-800 dark:text-green-300' : '',
          line.type === 'del' ? 'bg-red-500/15 text-red-800 dark:text-red-300' : '',
          line.type === 'skip' ? 'py-0.5 text-center text-muted-foreground select-none' : '',
        ]"
      >
        <template v-if="line.type === 'skip'">··· {{ line.count }} unchanged lines ···</template>
        <template v-else>{{ line.type === 'add' ? '+' : line.type === 'del' ? '-' : ' ' }} {{ line.text }}</template>
      </div>
    </div>
  </div>
</template>
