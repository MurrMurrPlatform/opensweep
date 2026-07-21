<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { AlertTriangle, Check, ChevronDown, ChevronRight, X } from 'lucide-vue-next'
import { MarkdownView } from '@/components/ui/markdown'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { areaKindVariant } from '@/lib/areas'
import { collapseContext, lineDiff } from '@/lib/lineDiff'
import type { AreaEditDTO } from '@/types/api'

const props = defineProps<{
  edit: AreaEditDTO
  /** Current scope paths of the target area — drives the scope add/remove diff
   *  (omit for new-area proposals; the whole set then reads as additions). */
  currentScopePaths?: string[]
  /** Partition warnings to eyeball before accepting (from a prior propose/accept). */
  warnings?: string[]
  /** This edit is being resolved right now (spinner on Accept). */
  resolving?: boolean
  /** Another resolution (single or bulk) is in flight — lock the buttons. */
  disabled?: boolean
}>()

defineEmits<{ accept: []; reject: [] }>()

const specOpen = ref(false)

const heading = computed(() => props.edit.title || props.edit.key)

/** Line diff of current → proposed spec, only when there's a current one to compare. */
const specDiff = computed(() =>
  props.edit.current_spec
    ? collapseContext(lineDiff(props.edit.current_spec, props.edit.proposed_spec || ''))
    : null,
)

/** Scope-path add/remove diff against the target area's current paths. */
const scopeDiff = computed(() => {
  const current = new Set(props.currentScopePaths ?? [])
  const proposed = new Set(props.edit.scope_paths)
  return {
    added: props.edit.scope_paths.filter((p) => !current.has(p)),
    removed: (props.currentScopePaths ?? []).filter((p) => !proposed.has(p)),
    unchanged: props.edit.scope_paths.filter((p) => current.has(p)),
    /** No current set given (new-area proposal) — render paths plainly, not as a diff. */
    isDiff: props.currentScopePaths != null,
  }
})
</script>

<template>
  <div class="border-b border-border p-4 last:border-b-0 space-y-2">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-1.5">
          <span class="font-mono text-sm font-medium">{{ edit.key }}</span>
          <Badge :variant="areaKindVariant(edit.kind)" class="px-1.5 text-[10px]">{{ edit.kind || 'subsystem' }}</Badge>
          <Badge v-if="!edit.area_uid" variant="info" class="px-1.5 text-[10px]">new area</Badge>
          <Badge v-else-if="edit.proposed_enabled === false" variant="destructive" class="px-1.5 text-[10px]">proposes retiring</Badge>
          <Badge v-else-if="edit.area_uid" variant="warn" class="px-1.5 text-[10px]" title="Replaces the area's current spec">updates existing</Badge>
        </div>
        <div v-if="heading !== edit.key" class="text-sm">{{ heading }}</div>
        <div class="text-xs text-muted-foreground">
          <span v-if="edit.source_run_uid">
            run
            <RouterLink
              :to="{ name: 'run-detail', params: { uid: edit.source_run_uid } }"
              class="font-mono text-primary hover:underline"
            >{{ edit.source_run_uid.slice(0, 8) }}</RouterLink>
          </span>
          <span v-if="edit.created_at"> · {{ edit.created_at.slice(0, 10) }}</span>
        </div>
      </div>
      <div class="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          :disabled="disabled || resolving"
          @click="$emit('reject')"
        >
          <X /> Reject
        </Button>
        <Button
          size="sm"
          :loading="resolving"
          :disabled="disabled"
          @click="$emit('accept')"
        >
          <Check /> Accept
        </Button>
      </div>
    </div>

    <p v-if="edit.rationale" class="text-sm text-muted-foreground">{{ edit.rationale }}</p>

    <!-- Partition warnings to eyeball before accepting -->
    <div
      v-if="warnings && warnings.length"
      class="rounded-sm border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-800 dark:text-amber-300"
    >
      <div class="mb-1 flex items-center gap-1 font-medium">
        <AlertTriangle class="h-3.5 w-3.5" /> Accepting this edit will:
      </div>
      <ul class="ml-4 list-disc space-y-0.5">
        <li v-for="(w, i) in warnings" :key="i">{{ w }}</li>
      </ul>
    </div>

    <!-- Scope paths: add/remove diff against the target area's current scope -->
    <div v-if="edit.scope_paths.length || scopeDiff.removed.length" class="flex flex-wrap gap-1.5">
      <span
        v-for="path in scopeDiff.added"
        :key="`+${path}`"
        class="rounded-full border font-mono text-xs px-2.5 py-0.5"
        :class="scopeDiff.isDiff ? 'border-green-500/40 bg-green-500/10 text-green-800 dark:text-green-300' : 'border-border'"
        :title="scopeDiff.isDiff ? 'Added path' : undefined"
      >
        <template v-if="scopeDiff.isDiff">+ </template>{{ path }}
      </span>
      <span
        v-for="path in scopeDiff.removed"
        :key="`-${path}`"
        class="rounded-full border border-red-500/40 bg-red-500/10 px-2.5 py-0.5 font-mono text-xs text-red-800 line-through dark:text-red-300"
        title="Removed path"
      >
        − {{ path }}
      </span>
      <span
        v-for="path in scopeDiff.unchanged"
        :key="`=${path}`"
        class="rounded-full border border-border px-2.5 py-0.5 font-mono text-xs"
      >
        {{ path }}
      </span>
    </div>

    <!-- Collapsible spec: line diff when replacing, plain preview otherwise -->
    <div v-if="edit.proposed_spec">
      <button
        type="button"
        class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        @click="specOpen = !specOpen"
      >
        <component :is="specOpen ? ChevronDown : ChevronRight" class="h-3.5 w-3.5" />
        {{ edit.current_spec ? 'Spec diff (current → proposed)' : 'Proposed spec' }}
      </button>
      <div v-if="specOpen" class="mt-2 space-y-2">
        <div
          v-if="specDiff"
          class="overflow-x-auto rounded-md border border-border bg-muted font-mono text-xs leading-5"
        >
          <div
            v-for="(line, i) in specDiff"
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
        <div v-else class="rounded-md border border-border p-3">
          <MarkdownView :model-value="edit.proposed_spec" preview-only />
        </div>
      </div>
    </div>
  </div>
</template>
