<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { AtSign, Bot, Check } from 'lucide-vue-next'
import { useCommentStore } from '@/stores/commentStore'
import { MENTION_TYPES, mentionToken } from '@/lib/mentions'
import { Button } from '@/components/ui/button'
import CommentBody from '@/components/comments/CommentBody.vue'
import type { MentionSearchResult, MentionTargetType } from '@/types/api'

/**
 * Comment textarea with an @-mention dropdown.
 *
 * Typing `@` opens the trigger menu: `@opensweep` summons the platform agent;
 * picking a data-item type (`@ticket`, `@finding`, …) opens a search panel
 * where multiple items can be selected and inserted as `@[Label](type:uid)`
 * tokens. Cmd/Ctrl+Enter submits.
 */
interface Props {
  modelValue: string
  rows?: number
  placeholder?: string
  disabled?: boolean
  repositoryUid?: string
}
const props = withDefaults(defineProps<Props>(), { rows: 3, placeholder: 'Write a comment…' })
const emit = defineEmits<{ 'update:modelValue': [value: string]; submit: [] }>()

const comments = useCommentStore()
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const searchRef = ref<HTMLInputElement | null>(null)

// GitHub-style Write / Preview toggle: bodies are markdown, so the composer
// offers a rendered preview without giving up the @-mention machinery.
const previewing = ref(false)
watch(
  () => props.modelValue,
  (v) => {
    if (!v.trim()) previewing.value = false // e.g. cleared after submit
  },
)

type Phase = 'closed' | 'types' | 'search'
const phase = ref<Phase>('closed')
const triggerStart = ref(-1) // index of the '@' in the body
const triggerEnd = ref(-1) // caret position when the menu opened / last typed
const highlighted = ref(0)

const searchType = ref<MentionTargetType>('ticket')
const searchQuery = ref('')
const searchResults = ref<MentionSearchResult[]>([])
const searchLoading = ref(false)
const selected = ref<MentionSearchResult[]>([])
let searchTimer: ReturnType<typeof setTimeout> | undefined

const typeFilter = computed(() =>
  phase.value === 'types' && triggerStart.value >= 0
    ? props.modelValue.slice(triggerStart.value + 1, triggerEnd.value).toLowerCase()
    : '',
)

interface TriggerOption {
  id: string
  label: string
  hint: string
  opensweep?: boolean
  type?: MentionTargetType
}
const triggerOptions = computed<TriggerOption[]>(() => {
  const options: TriggerOption[] = [
    { id: 'opensweep', label: '@opensweep', hint: 'summon OpenSweep on this thread', opensweep: true },
    ...MENTION_TYPES.map((t) => ({
      id: t.type,
      label: `@${t.type}`,
      hint: `mention a ${t.label.toLowerCase()}`,
      type: t.type,
    })),
  ]
  const filter = typeFilter.value
  return filter ? options.filter((o) => o.id.startsWith(filter)) : options
})

function closeMenu() {
  phase.value = 'closed'
  triggerStart.value = -1
  triggerEnd.value = -1
  highlighted.value = 0
  selected.value = []
  searchQuery.value = ''
  searchResults.value = []
}

function onInput(event: Event) {
  const el = event.target as HTMLTextAreaElement
  emit('update:modelValue', el.value)
  const caret = el.selectionStart ?? el.value.length
  const before = el.value.slice(0, caret)
  const match = /@(\w*)$/.exec(before)
  if (match && phase.value !== 'search') {
    triggerStart.value = caret - match[0].length
    triggerEnd.value = caret
    phase.value = 'types'
    highlighted.value = 0
  } else if (phase.value === 'types') {
    closeMenu()
  }
}

function replaceTrigger(insert: string) {
  const body = props.modelValue
  const next = body.slice(0, triggerStart.value) + insert + body.slice(triggerEnd.value)
  emit('update:modelValue', next)
  const caret = triggerStart.value + insert.length
  void nextTick(() => {
    textareaRef.value?.focus()
    textareaRef.value?.setSelectionRange(caret, caret)
  })
}

function pickTrigger(option: TriggerOption) {
  if (option.opensweep) {
    replaceTrigger('@opensweep ')
    closeMenu()
    return
  }
  searchType.value = option.type!
  phase.value = 'search'
  highlighted.value = 0
  selected.value = []
  searchQuery.value = ''
  void runSearch()
  void nextTick(() => searchRef.value?.focus())
}

async function runSearch() {
  searchLoading.value = true
  try {
    searchResults.value = await comments.searchMentions({
      q: searchQuery.value,
      types: [searchType.value],
      repository_uid: props.repositoryUid,
    })
  } catch {
    searchResults.value = []
  } finally {
    searchLoading.value = false
  }
}

watch(searchQuery, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => void runSearch(), 200)
})

function isSelected(item: MentionSearchResult): boolean {
  return selected.value.some((s) => s.type === item.type && s.uid === item.uid)
}

function toggle(item: MentionSearchResult) {
  selected.value = isSelected(item)
    ? selected.value.filter((s) => !(s.type === item.type && s.uid === item.uid))
    : [...selected.value, item]
}

function commitSelection() {
  if (!selected.value.length) {
    closeMenu()
    return
  }
  const tokens = selected.value.map((s) => mentionToken(s.type, s.uid, s.label)).join(' ')
  replaceTrigger(tokens + ' ')
  closeMenu()
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
    event.preventDefault()
    emit('submit')
    return
  }
  if (phase.value !== 'types') return
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    const n = triggerOptions.value.length
    if (n) {
      highlighted.value =
        (highlighted.value + (event.key === 'ArrowDown' ? 1 : n - 1)) % n
    }
  } else if (event.key === 'Enter' || event.key === 'Tab') {
    const option = triggerOptions.value[highlighted.value]
    if (option) {
      event.preventDefault()
      pickTrigger(option)
    }
  } else if (event.key === 'Escape') {
    event.preventDefault()
    closeMenu()
  }
}

function onSearchKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    const n = searchResults.value.length
    if (n) {
      highlighted.value =
        (highlighted.value + (event.key === 'ArrowDown' ? 1 : n - 1)) % n
    }
  } else if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
    event.preventDefault()
    commitSelection()
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const item = searchResults.value[highlighted.value]
    if (item) toggle(item)
  } else if (event.key === 'Escape') {
    event.preventDefault()
    closeMenu()
    textareaRef.value?.focus()
  }
}
</script>

<template>
  <div class="relative">
    <div class="mb-1 flex items-center gap-1">
      <button
        type="button"
        class="rounded px-2 py-0.5 text-xs font-medium transition-colors"
        :class="!previewing ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'"
        @click="previewing = false"
      >
        Write
      </button>
      <button
        type="button"
        class="rounded px-2 py-0.5 text-xs font-medium transition-colors"
        :class="previewing ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'"
        :disabled="!modelValue.trim()"
        @click="previewing = true"
      >
        Preview
      </button>
      <span class="ml-auto text-[11px] text-muted-foreground">Markdown supported</span>
    </div>

    <div
      v-if="previewing"
      class="min-h-[4.5rem] rounded-md border border-input bg-background px-3 py-2"
    >
      <CommentBody :body="modelValue" />
    </div>
    <textarea
      v-else
      ref="textareaRef"
      class="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
      :rows="rows"
      :placeholder="placeholder"
      :value="modelValue"
      :disabled="disabled"
      @input="onInput"
      @keydown="onKeydown"
    />

    <!-- Trigger menu: @opensweep + data-item types -->
    <div
      v-if="phase === 'types' && triggerOptions.length"
      class="animate-scale-in absolute left-0 top-full z-30 mt-1 w-64 rounded-md border bg-popover text-popover-foreground shadow-md"
    >
      <ul class="max-h-64 overflow-auto py-1">
        <li v-for="(option, i) in triggerOptions" :key="option.id">
          <button
            type="button"
            class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm"
            :class="i === highlighted ? 'bg-accent text-accent-foreground' : ''"
            @mouseenter="highlighted = i"
            @mousedown.prevent="pickTrigger(option)"
          >
            <Bot v-if="option.opensweep" class="size-3.5 text-primary" />
            <AtSign v-else class="size-3.5 text-muted-foreground" />
            <span class="font-medium">{{ option.label }}</span>
            <span class="ml-auto text-xs text-muted-foreground">{{ option.hint }}</span>
          </button>
        </li>
      </ul>
    </div>

    <!-- Search panel: multi-select items of the picked type -->
    <div
      v-if="phase === 'search'"
      class="animate-scale-in absolute left-0 top-full z-30 mt-1 w-80 rounded-md border bg-popover text-popover-foreground shadow-md"
    >
      <div class="border-b p-2">
        <input
          ref="searchRef"
          v-model="searchQuery"
          type="text"
          class="w-full rounded-sm border border-input bg-background px-2 py-1 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          :placeholder="`Search ${searchType.replace('_', ' ')}s… (Enter toggles, ⌘Enter inserts)`"
          @keydown="onSearchKeydown"
        />
      </div>
      <div v-if="searchLoading" class="px-3 py-2 text-sm text-muted-foreground">Searching…</div>
      <div v-else-if="!searchResults.length" class="px-3 py-2 text-sm text-muted-foreground">No matches.</div>
      <ul v-else class="max-h-56 overflow-auto py-1">
        <li v-for="(item, i) in searchResults" :key="`${item.type}:${item.uid}`">
          <button
            type="button"
            class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm"
            :class="i === highlighted ? 'bg-accent text-accent-foreground' : ''"
            @mouseenter="highlighted = i"
            @mousedown.prevent="toggle(item)"
          >
            <span
              class="flex size-4 shrink-0 items-center justify-center rounded-sm border"
              :class="isSelected(item) ? 'border-primary bg-primary text-primary-foreground' : ''"
            >
              <Check v-if="isSelected(item)" class="size-3" />
            </span>
            <span class="truncate">{{ item.label }}</span>
            <span class="ml-auto shrink-0 text-xs text-muted-foreground">{{ item.sublabel }}</span>
          </button>
        </li>
      </ul>
      <div class="flex items-center justify-between border-t p-2">
        <span class="text-xs text-muted-foreground">{{ selected.length }} selected</span>
        <div class="flex gap-2">
          <Button variant="ghost" size="sm" @mousedown.prevent="closeMenu()">Cancel</Button>
          <Button size="sm" :disabled="!selected.length" @mousedown.prevent="commitSelection()">
            Insert
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>
