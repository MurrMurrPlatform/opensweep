<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  Bot,
  CircleStop,
  History,
  Send,
  SquarePen,
  X,
} from 'lucide-vue-next'
import { useOpenSweepChatStore } from '@/stores/opensweepChatStore'
import { useRunStore } from '@/stores/runStore'
import { useRepositoryStore } from '@/stores/repositoryStore'
import { usePageContext } from '@/composables/usePageContext'
import { useRunSocket, type UseRunSocketOptions } from '@/composables/useRunSocket'
import { activityLabel } from '@/lib/opensweepActivity'
import { ApiError } from '@/services/api'
import { formatRelativeTime } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { MarkdownView } from '@/components/ui/markdown'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { RunStatus, RunTranscriptEvent } from '@/types/api'

/**
 * Platform-wide opensweep chat bubble (bottom-right). Hover expands the bubble
 * into a chat panel; a click pins it open. A conversation is a hidden chat
 * run (surface=chat) — multi-turn + streaming ride the normal run WS.
 *
 * The widget lives in ShellLayout, so the session (and its socket) survives
 * route navigation. The socket is only closed on session switch/unmount —
 * never on collapse, because closing a socket mid-turn interrupts the turn
 * it started.
 */

interface ChatMessage {
  id: number
  role: 'user' | 'opensweep' | 'activity' | 'error'
  text: string
}

const chat = useOpenSweepChatStore()
const runs = useRunStore()
const repos = useRepositoryStore()
const { context } = usePageContext()

// ── open/pin state ───────────────────────────────────────────────────────────

const hovering = ref(false)
const pinned = ref(false)
const inputFocused = ref(false)
const open = computed(() => pinned.value || hovering.value || inputFocused.value)

// ── panel view ───────────────────────────────────────────────────────────────

const view = ref<'chat' | 'history'>('chat')

// ── conversation state ───────────────────────────────────────────────────────

const messages = ref<ChatMessage[]>([])
const draft = ref('')
const busy = ref(false)
const runStatus = ref<RunStatus | null>(null)
const errorText = ref('')
const streamText = ref('')
const activity = ref('')
const scroller = ref<HTMLElement | null>(null)

/** Context chip: captured when the session starts, removable beforehand. */
const includeContext = ref(true)
const pickedRepoUid = ref('')

let nextId = 1
let lastSeq = 0
let socket: ReturnType<typeof useRunSocket> | null = null

const sessionTitle = computed(() => {
  const run = chat.sessions.find((r) => r.uid === chat.activeRunUid)
  return run?.title || 'New chat'
})

const needsRepoPick = computed(
  () =>
    !chat.activeRunUid &&
    !context.value.repositoryUid &&
    !(includeContext.value && context.value.subject),
)

const canSend = computed(
  () =>
    draft.value.trim().length > 0 &&
    !busy.value &&
    (!needsRepoPick.value || !!pickedRepoUid.value),
)

function scrollToBottom() {
  void nextTick(() => {
    scroller.value?.scrollTo({ top: scroller.value.scrollHeight })
  })
}

function push(role: ChatMessage['role'], text: string) {
  messages.value = [...messages.value, { id: nextId++, role, text }]
  scrollToBottom()
}

/** The chat preamble wraps the first user turn — show only what they typed. */
function stripPreamble(text: string): string {
  const marker = '## The maintainer says\n'
  const at = text.indexOf(marker)
  return at >= 0 ? text.slice(at + marker.length) : text
}

function applyEvent(event: RunTranscriptEvent) {
  if (event.seq) lastSeq = Math.max(lastSeq, event.seq)
  if (event.type === 'user_message') {
    const text = stripPreamble(event.text || '')
    // Skip the replay of a message we already rendered optimistically.
    const last = [...messages.value].reverse().find((m) => m.role === 'user')
    if (last?.text !== text) push('user', text)
    return
  }
  if (event.type === 'assistant_text') {
    streamText.value = ''
    activity.value = ''
    if (event.text) push('opensweep', event.text)
    return
  }
  if (event.type === 'tool_use') {
    activity.value = activityLabel(event) || ''
    return
  }
  if (event.type === 'error' && event.detail) {
    push('error', event.detail)
  }
}

const socketOptions: UseRunSocketOptions = {
  afterSeq: () => lastSeq,
  onEvent: applyEvent,
  onDelta(text) {
    streamText.value += text
    scrollToBottom()
  },
  onStatus(status) {
    runStatus.value = status
    if (status === 'running') {
      // The first turn starts after workspace prep flips the run through
      // awaiting_input — re-arm the typing indicator when it kicks in.
      busy.value = true
    } else if (status !== 'queued') {
      busy.value = false
      activity.value = ''
      streamText.value = ''
    }
  },
  onError(detail) {
    push('error', detail)
    busy.value = false
  },
  onUnavailable() {
    // REST fallback handles sends; nothing streams until reconnect.
  },
  onUnauthorized() {
    // Stale localStorage session (run deleted) — heal into a fresh chat.
    newChat()
  },
}

function connectTo(runUid: string) {
  socket?.close()
  socket = useRunSocket(runUid, socketOptions)
  socket.connect()
}

async function openSession(runUid: string) {
  chat.setActive(runUid)
  view.value = 'chat'
  messages.value = []
  streamText.value = ''
  activity.value = ''
  errorText.value = ''
  lastSeq = 0
  busy.value = false
  try {
    const transcript = await runs.getTranscript(runUid)
    transcript.events.forEach((e) => applyEvent(e as RunTranscriptEvent))
    lastSeq = transcript.last_seq || lastSeq
  } catch (e) {
    errorText.value = e instanceof ApiError ? e.detail : String(e)
  }
  connectTo(runUid)
}

function newChat() {
  socket?.close()
  socket = null
  chat.setActive(null)
  view.value = 'chat'
  messages.value = []
  streamText.value = ''
  activity.value = ''
  errorText.value = ''
  lastSeq = 0
  busy.value = false
  includeContext.value = true
}

async function send() {
  const text = draft.value.trim()
  if (!text || busy.value) return
  draft.value = ''
  errorText.value = ''
  busy.value = true
  push('user', text)
  try {
    if (!chat.activeRunUid) {
      const subject = includeContext.value ? context.value.subject : null
      const run = await chat.startSession({
        prompt: text,
        repositoryUid: context.value.repositoryUid || pickedRepoUid.value || null,
        context: subject
          ? { subject_type: subject.type, subject_uid: subject.uid }
          : undefined,
      })
      runStatus.value = run.status
      activity.value = 'setting up a workspace…'
      connectTo(run.uid)
      return
    }
    // Prefer the socket (streams deltas); fall back to the blocking REST turn.
    if (socket?.send(text)) return
    const result = await runs.sendMessage(chat.activeRunUid, text)
    if (result.error && !result.content) push('error', result.error)
    const transcript = await runs.getTranscript(chat.activeRunUid, lastSeq)
    transcript.events.forEach((e) => applyEvent(e as RunTranscriptEvent))
    lastSeq = transcript.last_seq || lastSeq
    busy.value = false
  } catch (e) {
    const msg = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)
    push('error', msg)
    busy.value = false
  }
}

function interrupt() {
  if (!chat.activeRunUid) return
  if (!socket?.sendInterrupt()) void runs.interrupt(chat.activeRunUid)
}

async function showHistory() {
  view.value = 'history'
  try {
    await chat.loadSessions()
  } catch {
    // list stays stale — harmless
  }
}

// Reopen the last session when the widget first expands.
let restored = false
watch(open, (isOpen) => {
  if (!isOpen || restored) return
  restored = true
  if (chat.activeRunUid) void openSession(chat.activeRunUid)
  void chat.loadSessions().catch(() => {})
  if (!repos.list.length) void repos.fetchAll().catch(() => {})
})

onBeforeUnmount(() => socket?.close())
</script>

<template>
  <div
    class="fixed bottom-4 right-4 z-40"
    @mouseenter="hovering = true"
    @mouseleave="hovering = false"
  >
    <!-- Collapsed bubble -->
    <button
      v-if="!open"
      type="button"
      class="flex size-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105"
      title="Chat with OpenSweep"
      @click="pinned = true"
    >
      <Bot class="size-6" />
    </button>

    <!-- Expanded panel -->
    <div
      v-else
      class="flex h-[560px] w-[380px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl"
    >
      <!-- Header -->
      <div class="flex items-center gap-2 border-b border-border px-3 py-2">
        <Bot class="size-4 shrink-0 text-primary" />
        <span class="min-w-0 flex-1 truncate text-sm font-medium">
          {{ view === 'history' ? 'Recent chats' : sessionTitle }}
        </span>
        <Button variant="ghost" size="icon" class="size-7" title="New chat" @click="newChat">
          <SquarePen class="size-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          class="size-7"
          title="Recent chats"
          @click="view === 'history' ? (view = 'chat') : showHistory()"
        >
          <History class="size-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          class="size-7"
          title="Close"
          @click="pinned = false; hovering = false; inputFocused = false"
        >
          <X class="size-4" />
        </Button>
      </div>

      <!-- History -->
      <div v-if="view === 'history'" class="flex-1 overflow-y-auto p-2">
        <div v-if="chat.sessionsLoading" class="p-3 text-sm text-muted-foreground">Loading…</div>
        <div v-else-if="!chat.sessions.length" class="p-3 text-sm text-muted-foreground">
          No chats yet — say hi.
        </div>
        <template v-else>
          <button
            v-for="s in chat.sessions"
            :key="s.uid"
            type="button"
            class="flex w-full flex-col gap-0.5 rounded-lg p-2 text-left transition-colors hover:bg-accent"
            :class="s.uid === chat.activeRunUid ? 'bg-accent' : ''"
            @click="openSession(s.uid)"
          >
            <span class="truncate text-sm">{{ s.title || `Chat ${s.uid.slice(0, 8)}` }}</span>
            <span class="text-xs text-muted-foreground">
              {{ formatRelativeTime(s.last_activity_at || s.created_at || undefined) }}
            </span>
          </button>
        </template>
      </div>

      <!-- Chat -->
      <template v-else>
        <div ref="scroller" class="flex-1 space-y-3 overflow-y-auto p-3">
          <div v-if="!messages.length" class="px-2 py-6 text-center text-sm text-muted-foreground">
            Ask OpenSweep anything about your data — it can look things up and
            make changes with the platform tools.
          </div>

          <div
            v-for="m in messages"
            :key="m.id"
            :class="m.role === 'user' ? 'flex justify-end' : ''"
          >
            <div
              v-if="m.role === 'user'"
              class="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-primary px-3 py-2 text-sm text-primary-foreground"
            >{{ m.text }}</div>
            <div
              v-else-if="m.role === 'opensweep'"
              class="max-w-[95%] rounded-2xl rounded-bl-sm bg-muted px-3 py-2 text-sm"
            >
              <MarkdownView :model-value="m.text" preview-only />
            </div>
            <div v-else-if="m.role === 'error'" class="text-xs text-destructive">
              {{ m.text }}
            </div>
          </div>

          <!-- Live stream / activity -->
          <div v-if="streamText" class="max-w-[95%] rounded-2xl rounded-bl-sm bg-muted px-3 py-2 text-sm">
            <MarkdownView :model-value="streamText" preview-only />
          </div>
          <div v-else-if="busy" class="flex items-center gap-2 text-sm text-muted-foreground">
            <span class="inline-flex gap-0.5">
              <span class="size-1 animate-bounce rounded-full bg-primary [animation-delay:0ms]" />
              <span class="size-1 animate-bounce rounded-full bg-primary [animation-delay:150ms]" />
              <span class="size-1 animate-bounce rounded-full bg-primary [animation-delay:300ms]" />
            </span>
            <span class="italic">{{ activity || 'thinking…' }}</span>
          </div>

          <div v-if="errorText" class="text-xs text-destructive">{{ errorText }}</div>
        </div>

        <!-- Context chip + repo picker (fresh chats only) -->
        <div v-if="!chat.activeRunUid" class="border-t border-border px-3 pt-2">
          <div v-if="includeContext && context.subject" class="flex items-center">
            <Badge variant="secondary" class="gap-1">
              {{ context.subject.label }}
              <button type="button" title="Remove context" @click="includeContext = false">
                <X class="size-3" />
              </button>
            </Badge>
          </div>
          <Select v-else-if="needsRepoPick" v-model="pickedRepoUid">
            <SelectTrigger class="h-8 w-full text-xs">
              <SelectValue placeholder="Pick a repository to chat about…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="r in repos.list" :key="r.uid" :value="r.uid">
                {{ r.slug || r.uid }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <!-- Composer -->
        <div class="flex items-end gap-2 p-3 pt-2">
          <Textarea
            v-model="draft"
            :rows="1"
            class="max-h-28 min-h-9 flex-1 resize-none text-sm"
            placeholder="Message OpenSweep…"
            @focus="inputFocused = true"
            @blur="inputFocused = false"
            @keydown.enter.exact.prevent="send"
          />
          <Button
            v-if="busy"
            variant="outline"
            size="icon"
            class="size-9 shrink-0"
            title="Stop"
            @click="interrupt"
          >
            <CircleStop class="size-4" />
          </Button>
          <Button
            v-else
            size="icon"
            class="size-9 shrink-0"
            :disabled="!canSend"
            title="Send"
            @click="send"
          >
            <Send class="size-4" />
          </Button>
        </div>
      </template>
    </div>
  </div>
</template>
