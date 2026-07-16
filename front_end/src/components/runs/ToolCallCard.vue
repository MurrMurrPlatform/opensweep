<script setup lang="ts">
/**
 * Claude-Code-style per-tool transcript card. Parses the tool input JSON and
 * renders a purpose-built body per tool family: real diffs for Edit/Write,
 * a terminal block for Bash, chips for Read/Grep, a checklist for TodoWrite,
 * and a key/value table for everything else. Falls back to raw <pre> display
 * whenever the input is not parseable JSON.
 */
import { computed, type FunctionalComponent } from 'vue'
import {
  Bot,
  CheckCircle2,
  ChevronRight,
  Circle,
  FilePen,
  FilePlus,
  FileText,
  FolderSearch,
  Globe,
  ListTodo,
  Loader2,
  Plug,
  Search,
  Terminal,
  TriangleAlert,
  Wrench,
} from 'lucide-vue-next'
import { DiffView } from '@/components/diff'

const props = defineProps<{
  name: string
  input: string
  output: string
  isError: boolean
  done: boolean
  live?: boolean
  ts?: string
}>()

// ---------------------------------------------------------------------------
// Input parsing & helpers
// ---------------------------------------------------------------------------

type Args = Record<string, unknown> | null

const args = computed<Args>(() => {
  if (!props.input) return null
  try {
    const parsed: unknown = JSON.parse(props.input)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
    return null
  } catch {
    return null
  }
})

/** Stringify any value for display (strings pass through, rest JSON'd). */
function asStr(v: unknown): string {
  if (typeof v === 'string') return v
  if (v === null || v === undefined) return ''
  try {
    return JSON.stringify(v)
  } catch {
    return String(v)
  }
}

function clip(s: string, n = 80): string {
  const flat = s.replace(/\s+/g, ' ').trim()
  return flat.length > n ? `${flat.slice(0, n)}…` : flat
}

// ---------------------------------------------------------------------------
// Tool classification
// ---------------------------------------------------------------------------

const mcp = computed<{ server: string; tool: string } | null>(() => {
  const m = /^mcp__(.+?)__(.+)$/.exec(props.name)
  return m ? { server: m[1], tool: m[2] } : null
})

const bareName = computed(() => (mcp.value ? mcp.value.tool : props.name))
const displayName = computed(() => (mcp.value ? `${mcp.value.server}: ${mcp.value.tool}` : props.name))

type Kind = 'edit' | 'write' | 'read' | 'bash' | 'search' | 'todos' | 'generic'

const kind = computed<Kind>(() => {
  const n = bareName.value.toLowerCase()
  if (['edit', 'multiedit', 'str_replace', 'str_replace_editor'].includes(n)) return 'edit'
  if (['write', 'create_file', 'create'].includes(n)) return 'write'
  if (['read', 'read_file', 'cat'].includes(n)) return 'read'
  if (['bash', 'shell', 'run_command', 'exec'].includes(n)) return 'bash'
  if (['grep', 'search', 'rg', 'glob'].includes(n)) return 'search'
  if (['todowrite', 'update_plan'].includes(n)) return 'todos'
  return 'generic'
})

/** Body layout: without parseable args, every kind degrades to generic. */
const bodyKind = computed<Kind>(() => (args.value ? kind.value : 'generic'))

const icon = computed<FunctionalComponent>(() => {
  if (mcp.value) return Plug
  const n = bareName.value.toLowerCase()
  switch (kind.value) {
    case 'edit':
      return FilePen
    case 'write':
      return FilePlus
    case 'read':
      return FileText
    case 'bash':
      return Terminal
    case 'search':
      return n === 'glob' ? FolderSearch : Search
    case 'todos':
      return ListTodo
    default:
      if (n === 'webfetch' || n === 'websearch') return Globe
      if (n === 'task' || n === 'agent') return Bot
      return Wrench
  }
})

// ---------------------------------------------------------------------------
// Derived fields
// ---------------------------------------------------------------------------

const filePath = computed(() => asStr(args.value?.file_path ?? args.value?.path))
const commandText = computed(() => asStr(args.value?.command))
const oldString = computed(() => asStr(args.value?.old_string))
const newString = computed(() => asStr(args.value?.new_string))
const replaceAll = computed(() => Boolean(args.value?.replace_all))
const contentText = computed(() => asStr(args.value?.content))

/** MultiEdit-style edits array, normalized. */
const edits = computed<{ oldText: string; newText: string; replaceAll: boolean }[] | null>(() => {
  const raw = args.value?.edits
  if (!Array.isArray(raw) || raw.length === 0) return null
  return raw.map((e) => {
    const o = e && typeof e === 'object' ? (e as Record<string, unknown>) : {}
    return { oldText: asStr(o.old_string), newText: asStr(o.new_string), replaceAll: Boolean(o.replace_all) }
  })
})

/** Todo checklist items (TodoWrite / update_plan). */
const todoItems = computed<{ status: string; text: string }[] | null>(() => {
  const raw = args.value?.todos ?? args.value?.items
  if (!Array.isArray(raw)) return null
  return raw.map((t) => {
    if (t && typeof t === 'object' && !Array.isArray(t)) {
      const o = t as Record<string, unknown>
      const text = asStr(o.content ?? o.subject ?? o.title ?? o.text ?? o.step) || asStr(t)
      return { status: asStr(o.status).toLowerCase(), text }
    }
    return { status: '', text: asStr(t) }
  })
})

/** Key/value chips for read/search bodies. */
const CHIP_KEYS = ['pattern', 'query', 'path', 'file_path', 'glob', 'offset', 'limit', 'output_mode', 'type', 'multiline'] as const

const chips = computed<{ key: string; value: string }[]>(() => {
  const a = args.value
  if (!a) return []
  return CHIP_KEYS.filter((k) => a[k] !== undefined && a[k] !== null && a[k] !== '').map((k) => ({
    key: k,
    value: asStr(a[k]),
  }))
})

/** All args as rows for the generic key/value table. */
const argEntries = computed<{ key: string; value: string }[]>(() =>
  args.value ? Object.entries(args.value).map(([key, v]) => ({ key, value: asStr(v) })) : [],
)

// ---------------------------------------------------------------------------
// Header summary
// ---------------------------------------------------------------------------

const summary = computed<string>(() => {
  const a = args.value
  if (!a) return ''
  const n = bareName.value.toLowerCase()
  switch (kind.value) {
    case 'edit':
    case 'write':
      return filePath.value
    case 'read': {
      let s = filePath.value
      const offset = a.offset
      const limit = a.limit
      if (s && (offset !== undefined || limit !== undefined)) {
        s += `:${asStr(offset ?? '')}-${asStr(limit ?? '')}`
      }
      return s
    }
    case 'bash':
      return clip(commandText.value, 80)
    case 'search': {
      const pattern = asStr(a.pattern ?? a.query)
      const path = asStr(a.path)
      return path ? `${clip(pattern, 60)} · ${path}` : clip(pattern, 80)
    }
    case 'todos':
      return todoItems.value ? `${todoItems.value.length} items` : ''
    default: {
      if (n === 'webfetch' || n === 'websearch') return clip(asStr(a.url ?? a.query), 80)
      if (n === 'task' || n === 'agent') return clip(asStr(a.description ?? a.prompt), 80)
      for (const key of ['file_path', 'path', 'command', 'pattern', 'query', 'url', 'title', 'name']) {
        if (typeof a[key] === 'string' && a[key]) return clip(a[key] as string, 80)
      }
      const firstString = Object.values(a).find((v): v is string => typeof v === 'string' && v.length > 0)
      return firstString ? clip(firstString, 80) : ''
    }
  }
})

// ---------------------------------------------------------------------------
// Output handling
// ---------------------------------------------------------------------------

/** Skip boilerplate like "The file X has been updated" on success. */
const showEditOutput = computed<boolean>(() => {
  const out = props.output.trim()
  if (!out) return false
  if (/has been (updated|created|written)/i.test(out) && out.length < 300) return false
  return true
})

const tsLabel = computed<string>(() => {
  if (!props.ts) return ''
  const d = new Date(props.ts)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
})
</script>

<template>
  <details class="tool-card" :class="{ 'tool-error': isError }">
    <summary class="tool-summary">
      <ChevronRight class="chevron h-3.5 w-3.5 shrink-0" />
      <component :is="icon" class="h-3.5 w-3.5 shrink-0 opacity-70" />
      <span class="font-mono font-medium shrink-0">{{ displayName }}</span>
      <span v-if="summary" class="tool-ctx" :title="summary">{{ summary }}</span>
      <span class="ml-auto flex items-center gap-2 shrink-0 pl-2">
        <span v-if="!done && live" class="flex items-center gap-1 text-muted-foreground">
          <Loader2 class="h-3 w-3 animate-spin" />
          <span class="text-[10px]">running</span>
        </span>
        <span v-else-if="isError" class="flex items-center gap-1 text-bad">
          <TriangleAlert class="h-3 w-3" />
          <span class="text-[10px]">error</span>
        </span>
        <span v-if="tsLabel" class="text-[10px] text-muted-foreground">{{ tsLabel }}</span>
      </span>
    </summary>

    <div class="tool-body">
      <!-- Edit / MultiEdit: real diffs from old/new string pairs -->
      <template v-if="bodyKind === 'edit'">
        <template v-if="edits">
          <div v-for="(e, i) in edits" :key="i" class="edit-block">
            <div class="tool-label">
              edit {{ i + 1 }}/{{ edits.length }}<template v-if="e.replaceAll"> · replace all</template>
            </div>
            <DiffView :old-text="e.oldText" :new-text="e.newText" :file="i === 0 ? filePath : ''" status="modified" max-height="280px" />
          </div>
        </template>
        <template v-else>
          <DiffView :old-text="oldString" :new-text="newString" :file="filePath" status="modified" max-height="320px" />
          <div v-if="replaceAll" class="tool-note">replace_all — every occurrence replaced</div>
        </template>
        <template v-if="isError">
          <div class="tool-label">error</div>
          <pre class="tool-pre text-bad">{{ output }}</pre>
        </template>
        <details v-else-if="showEditOutput" class="sub-disclosure">
          <summary>output</summary>
          <pre class="tool-pre">{{ output }}</pre>
        </details>
      </template>

      <!-- Write: full-content diff, all additions -->
      <template v-else-if="bodyKind === 'write'">
        <DiffView old-text="" :new-text="contentText" :file="filePath" status="added" max-height="320px" />
        <template v-if="isError">
          <div class="tool-label">error</div>
          <pre class="tool-pre text-bad">{{ output }}</pre>
        </template>
      </template>

      <!-- Bash: terminal block with $ command + output -->
      <template v-else-if="bodyKind === 'bash'">
        <div class="term">
          <div class="term-cmd"><span class="term-prompt">$</span> {{ commandText }}</div>
          <pre v-if="output" class="term-out" :class="{ 'term-err': isError }">{{ output }}</pre>
        </div>
      </template>

      <!-- Read / Grep / Glob: arg chips + output -->
      <template v-else-if="bodyKind === 'read' || bodyKind === 'search'">
        <div v-if="chips.length" class="chip-row">
          <span v-for="chip in chips" :key="chip.key" class="chip">
            <span class="chip-key">{{ chip.key }}</span>
            <span class="chip-val">{{ chip.value }}</span>
          </span>
        </div>
        <template v-if="output">
          <div class="tool-label">{{ isError ? 'error' : 'result' }}</div>
          <pre class="tool-pre" :class="{ 'text-bad': isError }">{{ output }}</pre>
        </template>
      </template>

      <!-- TodoWrite / update_plan: checklist -->
      <template v-else-if="bodyKind === 'todos'">
        <ul v-if="todoItems" class="todo-list">
          <li v-for="(item, i) in todoItems" :key="i" class="todo-item">
            <CheckCircle2 v-if="item.status === 'completed'" class="h-3.5 w-3.5 shrink-0 text-good" />
            <Loader2 v-else-if="item.status === 'in_progress'" class="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
            <Circle v-else class="h-3.5 w-3.5 shrink-0 text-muted-foreground opacity-60" />
            <span :class="{ 'line-through opacity-60': item.status === 'completed' }">{{ item.text }}</span>
          </li>
        </ul>
        <pre v-else class="tool-pre">{{ input }}</pre>
      </template>

      <!-- Anything else: key/value table (or raw input) + output -->
      <template v-else>
        <div v-if="argEntries.length" class="kv-wrap">
          <table class="kv-table">
            <tbody>
              <tr v-for="row in argEntries" :key="row.key">
                <td class="kv-key">{{ row.key }}</td>
                <td class="kv-val">{{ row.value }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <template v-else-if="input">
          <div class="tool-label">input</div>
          <pre class="tool-pre">{{ input }}</pre>
        </template>
        <template v-if="output">
          <div class="tool-label">{{ isError ? 'error' : 'result' }}</div>
          <pre class="tool-pre" :class="{ 'text-bad': isError }">{{ output }}</pre>
        </template>
        <div v-if="!input && !output" class="text-xs text-muted-foreground italic">No payload recorded.</div>
      </template>
    </div>
  </details>
</template>

<style scoped>
.tool-card {
  background: hsl(var(--muted) / 0.6);
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
  max-width: 85%;
}

.tool-card.tool-error {
  border-color: hsl(var(--destructive) / 0.5);
}

.tool-summary {
  align-items: center;
  cursor: pointer;
  display: flex;
  font-size: 12px;
  gap: 8px;
  list-style: none;
  min-width: 0;
  padding: 8px 12px;
  user-select: none;
}

.tool-summary::-webkit-details-marker {
  display: none;
}

.tool-card[open] .chevron {
  transform: rotate(90deg);
}

.chevron {
  transition: transform 0.15s ease;
}

.tool-ctx {
  color: hsl(var(--muted-foreground));
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-body {
  border-top: 1px solid hsl(var(--border));
  padding: 10px 12px;
}

.tool-label {
  color: hsl(var(--muted-foreground));
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 10px;
  margin: 6px 0 2px;
  text-transform: uppercase;
}

.tool-label:first-child {
  margin-top: 0;
}

.tool-note {
  color: hsl(var(--muted-foreground));
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 10px;
  font-style: italic;
  margin-top: 4px;
}

.tool-pre {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  line-height: 1.5;
  margin: 0;
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.edit-block + .edit-block {
  margin-top: 8px;
}

/* Nested "output" disclosure below diffs */
.sub-disclosure {
  margin-top: 6px;
}

.sub-disclosure > summary {
  color: hsl(var(--muted-foreground));
  cursor: pointer;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 10px;
  list-style: none;
  text-transform: uppercase;
  user-select: none;
}

.sub-disclosure > summary::-webkit-details-marker {
  display: none;
}

.sub-disclosure > summary::before {
  content: '▸ ';
}

.sub-disclosure[open] > summary::before {
  content: '▾ ';
}

.sub-disclosure[open] > .tool-pre {
  margin-top: 4px;
}

/* Terminal block (Bash) — mirrors RunDetailView's .terminal-* aesthetic */
.term {
  background: #0b0f14;
  border: 1px solid #243244;
  border-radius: 6px;
  overflow: hidden;
}

.term-cmd {
  color: #e5e7eb;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11.5px;
  line-height: 1.55;
  padding: 8px 10px;
  white-space: pre-wrap;
  word-break: break-word;
}

.term-prompt {
  color: #6ee7b7;
  user-select: none;
}

.term-out {
  border-top: 1px solid #1f2937;
  color: #d1fae5;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  line-height: 1.55;
  margin: 0;
  max-height: 280px;
  overflow: auto;
  padding: 8px 10px;
  white-space: pre-wrap;
  word-break: break-word;
}

.term-err {
  color: #fca5a5;
}

/* Key/value chips (Read / Grep / Glob) */
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 6px;
}

.chip {
  align-items: baseline;
  background: hsl(var(--muted));
  border: 1px solid hsl(var(--border));
  border-radius: 999px;
  display: inline-flex;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 10.5px;
  gap: 5px;
  max-width: 100%;
  padding: 2px 9px;
}

.chip-key {
  color: hsl(var(--muted-foreground));
  text-transform: uppercase;
  font-size: 9px;
}

.chip-val {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Todo checklist */
.todo-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
  list-style: none;
  margin: 0;
  padding: 0;
}

.todo-item {
  align-items: flex-start;
  display: flex;
  font-size: 12px;
  gap: 7px;
  line-height: 1.4;
}

.todo-item > svg {
  margin-top: 1.5px;
}

/* Generic key/value table */
.kv-wrap {
  max-height: 260px;
  overflow: auto;
}

.kv-table {
  border-collapse: collapse;
  font-size: 11px;
  width: 100%;
}

.kv-table td {
  padding: 2px 0;
  vertical-align: top;
}

.kv-key {
  color: hsl(var(--muted-foreground));
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 10px;
  padding-right: 12px !important;
  white-space: nowrap;
  width: 1%;
}

.kv-val {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
