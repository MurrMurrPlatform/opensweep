<script setup lang="ts">
/**
 * GitHub-style unified diff renderer. Feed it either a unified `patch`
 * string (backend-produced) or an `oldText`/`newText` pair (client-side
 * diff of Edit/Write tool inputs). Dual line-number gutters, +/- row
 * tinting, hunk separators, and an optional file header with add/del counts.
 */
import { computed } from 'vue'
import { FileDiff } from 'lucide-vue-next'
import { diffStats, rowsFromPatch, rowsFromStrings, type DiffRow } from '@/lib/diff'

const props = withDefaults(
  defineProps<{
    /** Unified diff text — wins over oldText/newText when set. */
    patch?: string
    oldText?: string
    newText?: string
    /** Optional file path shown in the header; header hidden when empty. */
    file?: string
    /** Status chip next to the file name (added / modified / deleted / renamed). */
    status?: string
    /** Max body height (CSS size). */
    maxHeight?: string
  }>(),
  { patch: '', oldText: '', newText: '', file: '', status: '', maxHeight: '420px' },
)

const rows = computed<DiffRow[]>(() =>
  props.patch ? rowsFromPatch(props.patch) : rowsFromStrings(props.oldText, props.newText),
)
const stats = computed(() => diffStats(rows.value))

const statusClass = computed(() => {
  const s = (props.status || '').toLowerCase()
  if (s.startsWith('a')) return 'chip-add'
  if (s.startsWith('d')) return 'chip-del'
  if (s.startsWith('r')) return 'chip-rename'
  return 'chip-mod'
})
</script>

<template>
  <div class="diff-view">
    <div v-if="file" class="diff-header">
      <FileDiff class="h-3.5 w-3.5 shrink-0 opacity-70" />
      <span class="diff-file" :title="file">{{ file }}</span>
      <span v-if="status" class="diff-chip" :class="statusClass">{{ status }}</span>
      <span class="ml-auto flex items-center gap-2 shrink-0">
        <span v-if="stats.additions" class="text-good">+{{ stats.additions }}</span>
        <span v-if="stats.deletions" class="text-bad">−{{ stats.deletions }}</span>
      </span>
    </div>
    <div class="diff-body" :style="{ maxHeight }">
      <table v-if="rows.length" class="diff-table">
        <tbody>
          <tr v-for="(row, i) in rows" :key="i" :class="`row-${row.type}`">
            <td class="gutter">{{ row.oldNo }}</td>
            <td class="gutter">{{ row.newNo }}</td>
            <td class="sign">
              {{ row.type === 'add' ? '+' : row.type === 'del' ? '−' : '' }}
            </td>
            <td class="code">{{ row.text }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="p-3 text-xs text-muted-foreground italic">No textual changes to show.</div>
    </div>
  </div>
</template>

<style scoped>
.diff-view {
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
  overflow: hidden;
}

.diff-header {
  align-items: center;
  background: hsl(var(--muted) / 0.8);
  border-bottom: 1px solid hsl(var(--border));
  display: flex;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  gap: 8px;
  padding: 6px 10px;
}

.diff-file {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.diff-chip {
  border-radius: 999px;
  flex-shrink: 0;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.04em;
  padding: 1px 7px;
  text-transform: uppercase;
}

.chip-add { background: color-mix(in srgb, var(--n-good) 15%, transparent); color: var(--n-good); }
.chip-del { background: color-mix(in srgb, var(--n-bad) 15%, transparent); color: var(--n-bad); }
.chip-mod { background: color-mix(in srgb, var(--n-warn) 15%, transparent); color: var(--n-warn); }
.chip-rename { background: hsl(var(--primary) / 0.15); color: hsl(var(--primary)); }

.diff-body {
  overflow: auto;
}

.diff-table {
  border-collapse: collapse;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11.5px;
  line-height: 1.6;
  width: 100%;
}

.diff-table td {
  padding: 0 8px;
  vertical-align: top;
}

.gutter {
  color: hsl(var(--muted-foreground) / 0.8);
  font-size: 10px;
  min-width: 34px;
  text-align: right;
  user-select: none;
  white-space: nowrap;
}

.sign {
  color: hsl(var(--muted-foreground));
  padding: 0 2px;
  user-select: none;
  width: 14px;
}

.code {
  white-space: pre-wrap;
  word-break: break-word;
  width: 100%;
}

.row-add { background: color-mix(in srgb, var(--n-good) 12%, transparent); }
.row-add .sign { color: var(--n-good); }
.row-del { background: color-mix(in srgb, var(--n-bad) 12%, transparent); }
.row-del .sign { color: var(--n-bad); }

.row-hunk {
  background: hsl(var(--primary) / 0.08);
  color: hsl(var(--muted-foreground));
}

.row-hunk .code {
  font-size: 10px;
  padding: 2px 8px;
}
</style>
