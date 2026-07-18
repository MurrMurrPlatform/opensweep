<script setup lang="ts">
/**
 * Subagent invocation card — a Task/Agent tool call rendered as what it is:
 * a child agent with its own task, progress and final report. Clicking opens
 * the drill-in modal with the full task prompt and the subagent's report.
 *
 * The executor streams subagent work as a single tool_use/tool_result pair,
 * so "progress" is running/done/failed; the report is the child's final text.
 */
import { computed, ref } from 'vue'
import { Bot, ChevronRight, CircleAlert, Loader2 } from 'lucide-vue-next'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogHeader,
  DialogScrollContent,
  DialogTitle,
} from '@/components/ui/dialog'
import { MarkdownView } from '@/components/ui/markdown'

const props = defineProps<{
  input: string
  output: string
  isError: boolean
  done: boolean
}>()

const open = ref(false)

/** Input may be a truncated JSON preview — parse defensively. */
const task = computed(() => {
  const fallback = { description: '', prompt: props.input, subagentType: '' }
  try {
    const parsed = JSON.parse(props.input) as Record<string, unknown>
    return {
      description: typeof parsed.description === 'string' ? parsed.description : '',
      prompt: typeof parsed.prompt === 'string' ? parsed.prompt : props.input,
      subagentType: typeof parsed.subagent_type === 'string' ? parsed.subagent_type : '',
    }
  } catch {
    const grab = (key: string) => {
      const m = new RegExp(`"${key}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"`).exec(props.input)
      return m ? m[1].replace(/\\n/g, '\n').replace(/\\"/g, '"') : ''
    }
    return {
      description: grab('description') || fallback.description,
      prompt: grab('prompt') || fallback.prompt,
      subagentType: grab('subagent_type') || fallback.subagentType,
    }
  }
})

const title = computed(() => task.value.description || 'Subagent task')

const statusLabel = computed(() => {
  if (!props.done) return 'working…'
  return props.isError ? 'failed' : 'done'
})
</script>

<template>
  <button
    type="button"
    class="flex w-full items-center gap-2.5 rounded-md border border-primary/25 bg-primary/5 px-3 py-2 text-left transition-colors hover:border-primary/50"
    @click="open = true"
  >
    <span class="relative flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
      <Bot class="size-4 text-primary" />
    </span>
    <span class="min-w-0 flex-1">
      <span class="flex items-center gap-2">
        <span class="truncate text-sm font-medium">{{ title }}</span>
        <Badge v-if="task.subagentType" variant="outline" class="px-1.5 text-[10px]">
          {{ task.subagentType }}
        </Badge>
      </span>
      <span class="block text-[11px] text-muted-foreground">
        subagent · {{ statusLabel }}
      </span>
    </span>
    <Loader2 v-if="!done" class="size-4 shrink-0 animate-spin text-primary" />
    <CircleAlert v-else-if="isError" class="size-4 shrink-0 text-destructive" />
    <ChevronRight v-else class="size-4 shrink-0 text-muted-foreground" />
  </button>

  <Dialog v-model:open="open">
    <DialogScrollContent class="max-w-3xl">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2">
          <Bot class="size-4 text-primary" />
          {{ title }}
          <Badge v-if="task.subagentType" variant="outline" class="px-1.5 text-[10px]">
            {{ task.subagentType }}
          </Badge>
          <Badge
            :variant="!done ? 'secondary' : isError ? 'destructive' : 'success'"
            class="px-1.5 text-[10px]"
          >
            {{ statusLabel }}
          </Badge>
        </DialogTitle>
      </DialogHeader>

      <div class="space-y-4">
        <section>
          <h3 class="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Task given to the subagent
          </h3>
          <div class="rounded-md border bg-muted/50 p-3">
            <MarkdownView :model-value="task.prompt" preview-only min-height="0" />
          </div>
        </section>

        <section>
          <h3 class="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Subagent report
          </h3>
          <div v-if="output" class="rounded-md border p-3" :class="isError ? 'border-destructive/40 bg-destructive/5' : ''">
            <MarkdownView :model-value="output" preview-only min-height="0" />
          </div>
          <p v-else class="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 class="size-3.5 animate-spin" /> The subagent is still working — its report
            lands here when it finishes.
          </p>
        </section>
      </div>
    </DialogScrollContent>
  </Dialog>
</template>
