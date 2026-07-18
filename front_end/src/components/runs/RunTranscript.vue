<script setup lang="ts">
/**
 * Structured run transcript (PLATFORM_V3_DESIGN.md §4): renders server-parsed
 * events as a conversation — prompt/prose bubbles, collapsible tool cards,
 * centered system pills. Never parses raw executor stdout.
 */
import { computed, nextTick, ref, watch } from 'vue'
import { Bot } from 'lucide-vue-next'
import { MarkdownView } from '@/components/ui/markdown'
import ToolCallCard from '@/components/runs/ToolCallCard.vue'
import WorkingIndicator from '@/components/runs/WorkingIndicator.vue'
import type { RunTranscriptEvent } from '@/types/api'

const props = defineProps<{
  events: RunTranscriptEvent[]
  /** Run still producing output — shows the working indicator and sticks scroll. */
  live?: boolean
  /** Assistant tokens streamed over the WebSocket for the in-flight turn —
   *  rendered as a live bubble below the settled events. */
  streamingText?: string
  /** Narrated mode: tool calls render as plain-language narration lines that
   *  expand to the raw card on click (unified dev flow Phase 2). */
  narrated?: boolean
}>()

type Item =
  | { kind: 'user'; text: string; ts: string }
  | { kind: 'assistant'; text: string; ts: string }
  | { kind: 'tool'; name: string; input: string; output: string; isError: boolean; done: boolean; ts: string; narration: string; seq: number }
  | { kind: 'system'; text: string; ts: string }
  | { kind: 'turn_end'; status: string; usage: Record<string, unknown>; ts: string }
  | { kind: 'error'; detail: string; ts: string }

/** Fold the event stream into renderable items: consecutive assistant_text
 *  chunks merge into one bubble; a tool_result attaches to its pending
 *  tool_use card (matched by name, most recent first); a narration line
 *  attaches to the tool_use it covers (matched by covers_seq). */
const items = computed<Item[]>(() => {
  const out: Item[] = []
  for (const e of props.events) {
    const ts = e.ts || ''
    if (e.type === 'assistant_text') {
      const last = out[out.length - 1]
      if (last?.kind === 'assistant') last.text += e.text || ''
      else out.push({ kind: 'assistant', text: e.text || '', ts })
    } else if (e.type === 'user_message') {
      out.push({ kind: 'user', text: e.text || '', ts })
    } else if (e.type === 'tool_use') {
      out.push({ kind: 'tool', name: e.name || '?', input: e.input || '', output: '', isError: false, done: false, ts, narration: '', seq: e.seq })
    } else if (e.type === 'narration') {
      const covered = [...out].reverse().find(
        (i): i is Extract<Item, { kind: 'tool' }> => i.kind === 'tool' && i.seq === (e.covers_seq ?? -1),
      )
      if (covered) covered.narration = e.text || ''
    } else if (e.type === 'tool_result') {
      const pending = [...out].reverse().find(
        (i): i is Extract<Item, { kind: 'tool' }> => i.kind === 'tool' && !i.done && i.name === (e.name || '?'),
      )
      if (pending) {
        pending.output = e.output || ''
        pending.isError = Boolean(e.is_error)
        pending.done = true
      } else {
        out.push({ kind: 'tool', name: e.name || '?', input: '', output: e.output || '', isError: Boolean(e.is_error), done: true, ts, narration: '', seq: e.seq })
      }
    } else if (e.type === 'system') {
      out.push({ kind: 'system', text: e.text || '', ts })
    } else if (e.type === 'turn_end') {
      out.push({ kind: 'turn_end', status: e.status || '', usage: e.usage || {}, ts })
    } else if (e.type === 'error') {
      out.push({ kind: 'error', detail: e.detail || '', ts })
    }
  }
  return out
})

const USER_PREVIEW_CHARS = 400
const expandedUsers = ref(new Set<number>())

function userPreview(text: string): string {
  return text.length <= USER_PREVIEW_CHARS ? text : `${text.slice(0, USER_PREVIEW_CHARS).trimEnd()}…`
}

function toggleUser(idx: number) {
  const next = new Set(expandedUsers.value)
  if (next.has(idx)) next.delete(idx)
  else next.add(idx)
  expandedUsers.value = next
}

function fmtTs(ts: string): string {
  const d = new Date(ts)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

// Narrated mode: which narration lines are expanded into their raw card.
const expandedTools = ref(new Set<number>())

function toggleTool(idx: number) {
  const next = new Set(expandedTools.value)
  if (next.has(idx)) next.delete(idx)
  else next.add(idx)
  expandedTools.value = next
}

function narrationLabel(item: Extract<Item, { kind: 'tool' }>): string {
  return item.narration || `Using the ${item.name} tool`
}

function turnEndLabel(item: Extract<Item, { kind: 'turn_end' }>): string {
  const bits = [item.status || 'turn finished']
  const ms = item.usage?.duration_ms
  if (typeof ms === 'number') bits.push(`${(ms / 1000).toFixed(1)}s`)
  const turns = item.usage?.num_turns
  if (typeof turns === 'number') bits.push(`${turns} turns`)
  return bits.join(' · ')
}

/** Label for the working indicator: names the in-flight tool when one is running. */
const workingLabel = computed<string>(() => {
  const last = items.value[items.value.length - 1]
  if (last?.kind === 'tool' && !last.done) {
    const m = /^mcp__(.+?)__(.+)$/.exec(last.name)
    return `Running ${m ? m[2] : last.name}`
  }
  if (last?.kind === 'user') return 'Thinking'
  return 'Working'
})

// Stick to the bottom while live until the user scrolls up.
const scrollEl = ref<HTMLElement | null>(null)
const stick = ref(true)

function onScroll() {
  const el = scrollEl.value
  if (!el) return
  stick.value = el.scrollHeight - el.scrollTop - el.clientHeight < 40
}

watch(
  () => [props.events.length, props.streamingText?.length ?? 0],
  async () => {
    await nextTick()
    const el = scrollEl.value
    if (el && stick.value) el.scrollTop = el.scrollHeight
  },
)
</script>

<template>
  <div ref="scrollEl" class="transcript overflow-y-auto p-5 space-y-4" @scroll="onScroll">
    <div v-if="items.length === 0 && !streamingText" class="h-full grid place-items-center py-10">
      <div class="text-center text-sm text-muted-foreground max-w-sm">
        <Bot class="h-8 w-8 mx-auto mb-2" />
        <template v-if="live">Waiting for agent output…</template>
        <template v-else>No structured transcript for this run — check the Raw tab.</template>
      </div>
    </div>

    <template v-for="(item, idx) in items" :key="idx">
      <!-- Dispatched prompt / follow-up: right-aligned bubble, collapsed when long -->
      <div v-if="item.kind === 'user'" class="flex justify-end">
        <div class="max-w-[85%]">
          <div class="rounded-md rounded-br-sm bg-primary/10 border border-primary/20 px-4 py-2.5 whitespace-pre-wrap break-words font-mono text-xs">
            {{ expandedUsers.has(idx) ? item.text : userPreview(item.text) }}
          </div>
          <div class="mt-1 flex items-center justify-end gap-2 text-[10px] text-muted-foreground">
            <button
              v-if="item.text.length > USER_PREVIEW_CHARS"
              class="text-primary hover:underline"
              @click="toggleUser(idx)"
            >
              {{ expandedUsers.has(idx) ? 'Show less' : 'Show full prompt' }}
            </button>
            <span>{{ fmtTs(item.ts) }}</span>
          </div>
        </div>
      </div>

      <!-- Agent prose: left-aligned markdown bubble -->
      <div v-else-if="item.kind === 'assistant'" class="flex justify-start">
        <div class="max-w-[85%] min-w-0">
          <div class="rounded-md rounded-bl-sm bg-muted border px-4 py-2.5 text-sm">
            <MarkdownView :model-value="item.text" preview-only min-height="0" />
          </div>
          <div class="mt-1 text-[10px] text-muted-foreground">{{ fmtTs(item.ts) }}</div>
        </div>
      </div>

      <!-- Tool call, narrated: plain-language line, click to expand the raw card -->
      <div v-else-if="item.kind === 'tool' && narrated" class="narration-item">
        <button
          type="button"
          class="flex w-full items-center gap-2 text-left text-xs text-muted-foreground hover:text-foreground"
          @click="toggleTool(idx)"
        >
          <span
            class="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
            :class="item.isError ? 'bg-destructive' : item.done ? 'bg-primary/50' : 'bg-primary animate-pulse'"
          />
          <span class="min-w-0 flex-1 truncate">{{ narrationLabel(item) }}</span>
          <span class="shrink-0 text-[10px]">{{ expandedTools.has(idx) ? 'hide' : 'detail' }}</span>
        </button>
        <ToolCallCard
          v-if="expandedTools.has(idx)"
          class="mt-1.5"
          :name="item.name"
          :input="item.input"
          :output="item.output"
          :is-error="item.isError"
          :done="item.done"
          :live="live"
          :ts="item.ts"
        />
      </div>

      <!-- Tool call: collapsible per-tool card -->
      <ToolCallCard
        v-else-if="item.kind === 'tool'"
        :name="item.name"
        :input="item.input"
        :output="item.output"
        :is-error="item.isError"
        :done="item.done"
        :live="live"
        :ts="item.ts"
      />

      <!-- System marker: centered pill -->
      <div v-else-if="item.kind === 'system'" class="text-center">
        <span class="inline-block rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">
          {{ item.text }}
        </span>
      </div>

      <!-- Turn boundary -->
      <div v-else-if="item.kind === 'turn_end'" class="turn-divider">
        <span>{{ turnEndLabel(item) }}</span>
      </div>

      <!-- Error -->
      <div v-else-if="item.kind === 'error'" class="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs">
        {{ item.detail }}
      </div>
    </template>

    <!-- Streaming assistant turn — grows with each WS delta -->
    <div v-if="streamingText" class="flex justify-start">
      <div class="max-w-[85%] min-w-0">
        <div class="rounded-md rounded-bl-sm bg-muted border px-4 py-2.5 text-sm">
          <MarkdownView :model-value="streamingText" preview-only min-height="0" />
          <span class="inline-block w-2 h-4 bg-primary/60 animate-pulse mt-0.5" />
        </div>
        <div class="mt-1 text-[10px] text-muted-foreground">streaming…</div>
      </div>
    </div>

    <!-- Working indicator while the run streams -->
    <div v-else-if="live" class="flex justify-start">
      <WorkingIndicator :label="workingLabel" />
    </div>
  </div>
</template>

<style scoped>
.transcript {
  max-height: 560px;
  min-height: 320px;
}

.turn-divider {
  align-items: center;
  color: hsl(var(--muted-foreground));
  display: flex;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 10px;
  gap: 12px;
  text-transform: uppercase;
}

.turn-divider::before,
.turn-divider::after {
  background: hsl(var(--border));
  content: '';
  flex: 1;
  height: 1px;
}
</style>
