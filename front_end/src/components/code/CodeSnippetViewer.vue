<script setup lang="ts">
import { computed, nextTick, onMounted, ref, shallowRef, watch } from 'vue'
import { apiGet, ApiError } from '@/services/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Maximize2,
  Minimize2,
} from 'lucide-vue-next'
import type { FileContent } from '@/types/api'

const props = withDefaults(defineProps<{
  repositoryUid: string
  path: string
  startLine?: number
  endLine?: number
  /** Absolute line numbers to highlight (with a left bar + tinted background). */
  highlightLines?: number[]
  /**
   * Identifier strings extracted from the finding text. Any line in the
   * loaded content containing one of these is also highlighted — robust against
   * the LLM emitting off-by-N line numbers in affected_paths.
   */
  searchHints?: string[]
  /** Render collapsed by default. */
  collapsedByDefault?: boolean
  /** Optional external link (e.g. github URL). */
  externalUrl?: string | null
}>(), {
  collapsedByDefault: false,
  highlightLines: () => [],
  searchHints: () => [],
})

type ViewMode = 'range' | 'full'

const hasRange = computed(() => Boolean(props.startLine || props.endLine))
const open = ref(!props.collapsedByDefault)
const loading = ref(false)
const error = ref<string | null>(null)
const file = ref<FileContent | null>(null)
const highlighted = shallowRef<string>('')
const viewMode = ref<ViewMode>(hasRange.value ? 'range' : 'full')
const containerRef = ref<HTMLElement | null>(null)

const SUPPORTED_LANGS = new Set([
  'python', 'javascript', 'jsx', 'typescript', 'tsx', 'vue', 'go', 'rust',
  'java', 'ruby', 'php', 'c', 'cpp', 'csharp', 'kotlin', 'swift', 'scala',
  'bash', 'yaml', 'toml', 'json', 'markdown', 'html', 'css', 'scss', 'sql',
  'dockerfile',
])

const highlightSet = computed(() => {
  const set = new Set<number>(props.highlightLines || [])
  if (file.value && props.searchHints?.length) {
    const startNum = file.value.start_line || 1
    const lines = file.value.content.split('\n')
    const hints = props.searchHints
    for (let i = 0; i < lines.length; i++) {
      const text = lines[i]
      for (const h of hints) {
        if (h && text.includes(h)) {
          set.add(startNum + i)
          break
        }
      }
    }
  }
  return set
})

const lineRangeLabel = computed(() => {
  if (!file.value) return ''
  const { start_line, end_line, total_lines } = file.value
  if (start_line === 1 && end_line === total_lines) return `${total_lines} lines`
  return `lines ${start_line}–${end_line} of ${total_lines}`
})

const plainLines = computed(() => {
  if (!file.value) return [] as { num: number; text: string; highlighted: boolean }[]
  const startNum = file.value.start_line || 1
  return file.value.content.split('\n').map((text, i) => {
    const num = startNum + i
    return { num, text, highlighted: highlightSet.value.has(num) }
  })
})

const gutterWidth = computed(() => {
  const last = file.value
    ? (file.value.start_line || 1) + Math.max(0, file.value.content.split('\n').length - 1)
    : 0
  return Math.max(2, String(last).length)
})

async function load() {
  loading.value = true
  error.value = null
  try {
    const qs = new URLSearchParams({ path: props.path })
    if (viewMode.value === 'range') {
      if (props.startLine) qs.set('start_line', String(props.startLine))
      if (props.endLine) qs.set('end_line', String(props.endLine))
    }
    file.value = await apiGet<FileContent>(
      `/repositories/${props.repositoryUid}/file?${qs.toString()}`,
    )
    await renderHighlight()
    await scrollToFirstHighlight()
  } catch (e: unknown) {
    file.value = null
    highlighted.value = ''
    if (e instanceof ApiError) {
      error.value = e.detail
    } else if (e instanceof Error) {
      error.value = e.message
    } else {
      error.value = 'Failed to load file'
    }
  } finally {
    loading.value = false
  }
}

async function renderHighlight() {
  if (!file.value) return
  const lang = (file.value.language || '').toLowerCase()
  if (!SUPPORTED_LANGS.has(lang)) {
    highlighted.value = ''
    return
  }
  try {
    const { codeToHtml } = await import('shiki')
    const startNum = file.value.start_line || 1
    const width = gutterWidth.value
    const hl = highlightSet.value
    highlighted.value = await codeToHtml(file.value.content, {
      lang,
      theme: 'github-dark-dimmed',
      transformers: [
        {
          name: 'opensweep-line-decorations',
          line(node, lineIdx) {
            const lineNum = startNum + lineIdx - 1
            node.children.unshift({
              type: 'element',
              tagName: 'span',
              properties: {
                class: 'line-num',
                style: `width: ${width}ch`,
              },
              children: [{ type: 'text', value: String(lineNum) }],
            })
            if (hl.has(lineNum)) {
              const cur = node.properties.class
              const tokens = Array.isArray(cur)
                ? cur.map(String)
                : typeof cur === 'string'
                  ? cur.split(/\s+/).filter(Boolean)
                  : []
              tokens.push('line-highlight')
              node.properties.class = tokens.join(' ')
            }
            node.properties['data-line'] = String(lineNum)
          },
        },
      ],
    })
  } catch {
    highlighted.value = ''
  }
}

async function scrollToFirstHighlight() {
  if (!highlightSet.value.size) return
  await nextTick()
  const el = containerRef.value?.querySelector<HTMLElement>('.line-highlight')
  if (el) {
    el.scrollIntoView({ block: 'center', behavior: 'auto' })
  }
}

function toggleMode() {
  viewMode.value = viewMode.value === 'range' ? 'full' : 'range'
  file.value = null
  highlighted.value = ''
  load()
}

onMounted(() => {
  if (open.value) load()
})
watch(open, (v) => {
  if (v && !file.value && !loading.value) load()
})
watch(() => [props.repositoryUid, props.path, props.startLine, props.endLine], () => {
  file.value = null
  highlighted.value = ''
  viewMode.value = hasRange.value ? 'range' : 'full'
  if (open.value) load()
})
watch(() => [props.highlightLines, props.searchHints], async () => {
  if (file.value) {
    await renderHighlight()
    await scrollToFirstHighlight()
  }
})
</script>

<template>
  <div class="border rounded-sm overflow-hidden bg-muted min-w-0">
    <button
      type="button"
      class="w-full flex items-center justify-between px-3 py-2 hover:bg-accent text-left"
      @click="open = !open"
    >
      <div class="flex items-center gap-2 min-w-0">
        <ChevronDown v-if="open" class="h-4 w-4 text-muted-foreground shrink-0" />
        <ChevronRight v-else class="h-4 w-4 text-muted-foreground shrink-0" />
        <span class="font-mono text-xs text-foreground truncate">{{ path }}</span>
        <Badge v-if="file" variant="outline" class="px-1.5 text-[10px]">{{ file.source }}</Badge>
        <Badge v-if="file?.language" variant="info" class="px-1.5 text-[10px]">{{ file.language }}</Badge>
        <span v-if="file" class="text-muted-foreground text-xs whitespace-nowrap">{{ lineRangeLabel }}</span>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <button
          v-if="open && hasRange && file"
          type="button"
          class="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
          :title="viewMode === 'range' ? 'Expand to full file' : 'Show focused range'"
          @click.stop="toggleMode"
        >
          <Maximize2 v-if="viewMode === 'range'" class="h-3.5 w-3.5" />
          <Minimize2 v-else class="h-3.5 w-3.5" />
          <span>{{ viewMode === 'range' ? 'Full file' : 'Focus' }}</span>
        </button>
        <a
          v-if="externalUrl"
          :href="externalUrl"
          target="_blank"
          rel="noopener noreferrer"
          class="text-muted-foreground hover:text-foreground"
          @click.stop
        >
          <ExternalLink class="h-4 w-4" />
        </a>
      </div>
    </button>

    <div v-if="open" ref="containerRef" class="code-container">
      <div v-if="loading" class="p-3"><Skeleton class="h-24" /></div>
      <div v-else-if="error" class="px-3 py-2 text-bad text-sm">
        {{ error }}
        <Button size="sm" variant="ghost" class="ml-2" @click="load">Retry</Button>
      </div>
      <div v-else-if="file && highlighted" class="code-snippet" v-html="highlighted" />
      <pre
        v-else-if="file"
        class="code-plain"
      ><div
          v-for="line in plainLines"
          :key="line.num"
          class="line"
          :class="{ 'line-highlight': line.highlighted }"
          :data-line="line.num"
        ><span class="line-num" :style="{ width: gutterWidth + 'ch' }">{{ line.num }}</span><span class="line-text">{{ line.text }}</span></div></pre>
      <div v-if="file?.truncated" class="px-3 py-1 text-muted-foreground text-xs border-t">
        Content truncated.
      </div>
    </div>
  </div>
</template>

<style>
.code-snippet pre,
.code-container .code-plain {
  margin: 0;
  padding: 0.25rem 0;
  overflow-x: auto;
  font-size: 0.75rem;
  line-height: 1.35;
  background: transparent;
  /* Collapse the literal "\n" text nodes shiki keeps between .line spans,
     so block-displayed lines don't get a phantom empty row between them. */
  white-space: normal;
}
.code-snippet code,
.code-container .code-plain {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  display: block;
  white-space: normal;
}
.code-snippet .line,
.code-container .code-plain .line {
  display: block;
  padding: 0 0.75rem 0 0;
  min-width: 100%;
  width: max-content;
  /* Preserve indentation inside a line (the parent collapses inter-line space). */
  white-space: pre;
}
.code-snippet .line-num,
.code-container .code-plain .line-num {
  display: inline-block;
  padding: 0 0.75rem 0 0.5rem;
  margin-right: 0.75rem;
  text-align: right;
  color: rgba(148, 163, 184, 0.5);
  user-select: none;
  border-right: 1px solid rgba(148, 163, 184, 0.18);
}
.code-snippet .line-highlight,
.code-container .code-plain .line.line-highlight {
  background: rgba(250, 204, 21, 0.10);
  box-shadow: inset 2px 0 0 #facc15;
}
.code-snippet .line-highlight .line-num,
.code-container .code-plain .line.line-highlight .line-num {
  color: rgba(250, 204, 21, 0.9);
  border-right-color: rgba(250, 204, 21, 0.45);
}
.code-container .code-plain .line-text {
  white-space: pre;
}
</style>
