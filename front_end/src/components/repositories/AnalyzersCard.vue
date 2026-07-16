<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ScanLine, Plus, Trash2 } from 'lucide-vue-next'
import { useWorkflowStore } from '@/stores/workflowStore'
import { useToast } from '@/composables/useToast'
import { ApiError } from '@/services/api'
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import type { AnalyzerMode, AnalyzersConfig } from '@/types/api'

interface Props {
  repositoryUid: string
}
const props = defineProps<Props>()

const workflow = useWorkflowStore()
const toast = useToast()

// Mirrors ANALYZER_TOOLS in back_end/domains/execution/services/static_analysis.py.
// The backend 422s on any tool outside this set, so the picker is the source of truth.
const TOOL_OPTIONS = [
  { label: 'ruff (Python lint)', value: 'ruff' },
  { label: 'vulture (Python dead code)', value: 'vulture' },
  { label: 'deptry (Python deps)', value: 'deptry' },
  { label: 'semgrep (multi-language)', value: 'semgrep' },
  { label: 'knip (JS/TS dead code)', value: 'knip' },
]
const DEFAULT_TOOL = TOOL_OPTIONS[0].value

// Local editable row: args/paths are string lists on the wire, edited as
// whitespace-separated text for a compact single-line editor.
interface EditableTool {
  tool: string
  argsText: string
  pathsText: string
}

const config = ref<AnalyzersConfig | null>(null)
const mode = ref<AnalyzerMode>('auto')
const tools = ref<EditableTool[]>([])
const loading = ref(true)
const saving = ref(false)
const loadError = ref<string | null>(null)

const MODE_OPTIONS = [
  { label: 'Auto — detect and run the toolchain’s linters', value: 'auto' },
  { label: 'Custom — run only the tools configured below', value: 'custom' },
  { label: 'Off — no static analysis on this repo', value: 'off' },
]

const MODE_HELP: Record<AnalyzerMode, string> = {
  auto: 'OpenSweep picks analyzers from the detected languages and runs them on review/fix runs.',
  custom: 'Only the tools configured below run on review/fix runs.',
  off: 'Static analysis is skipped entirely; reviews rely on the LLM pass alone.',
}

function splitTokens(text: string): string[] {
  return text.split(/\s+/).filter(Boolean)
}

function toEditable(t: AnalyzersConfig['tools'][number]): EditableTool {
  return { tool: t.tool, argsText: t.args.join(' '), pathsText: t.paths.join(' ') }
}

function toWire(): AnalyzersConfig['tools'] {
  return tools.value.map((t) => ({
    tool: t.tool,
    args: splitTokens(t.argsText),
    paths: splitTokens(t.pathsText),
  }))
}

function hydrate(c: AnalyzersConfig) {
  config.value = c
  mode.value = c.mode
  tools.value = c.tools.map(toEditable)
}

const dirty = computed(() => {
  if (!config.value) return false
  if (mode.value !== config.value.mode) return true
  // Tool edits only matter in custom mode (the only mode that persists them).
  if (mode.value !== 'custom') return false
  return JSON.stringify(toWire()) !== JSON.stringify(config.value.tools)
})

function addTool() {
  tools.value.push({ tool: DEFAULT_TOOL, argsText: '', pathsText: '' })
}

function removeTool(index: number) {
  tools.value.splice(index, 1)
}

async function load() {
  loading.value = true
  loadError.value = null
  try {
    hydrate(await workflow.fetchAnalyzers(props.repositoryUid))
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.repositoryUid, () => void load())

async function save() {
  if (saving.value || !config.value) return
  saving.value = true
  try {
    // Preserve tools when not in custom mode (backend only runs them there,
    // but keeps them so switching back to custom doesn't lose the config).
    const payload: AnalyzersConfig = {
      mode: mode.value,
      tools: mode.value === 'custom' ? toWire() : config.value.tools,
    }
    hydrate(await workflow.updateAnalyzers(props.repositoryUid, payload))
    toast.success('Analyzers saved')
  } catch (e) {
    const msg = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)
    toast.error('Couldn’t save analyzers', msg)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Card>
    <CardHeader class="flex-col gap-3 sm:flex-row sm:items-start sm:justify-between space-y-0">
      <div>
        <CardTitle class="flex items-center gap-2 text-base">
          <ScanLine class="h-4 w-4 text-muted-foreground" /> Static analyzers
        </CardTitle>
        <div class="text-xs text-muted-foreground mt-0.5">
          Controls whether review and fix runs run static-analysis tools alongside the LLM pass.
        </div>
      </div>
      <Button
        size="sm"
        class="shrink-0"
        :disabled="loading || !config || !dirty"
        :loading="saving"
        @click="save"
      >
        Save
      </Button>
    </CardHeader>
    <CardContent>
      <div v-if="loading" class="text-sm text-muted-foreground">Loading analyzers…</div>
      <div v-else-if="loadError" class="text-sm text-muted-foreground">
        Couldn’t load analyzers: {{ loadError }}
        <Button variant="outline" size="sm" class="ml-2" @click="load">Retry</Button>
      </div>
      <div v-else-if="config" class="space-y-3 text-sm">
        <Select :model-value="mode" @update:model-value="mode = $event as AnalyzerMode">
          <SelectTrigger class="w-full max-w-md">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="o in MODE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</SelectItem>
          </SelectContent>
        </Select>
        <p class="text-xs text-muted-foreground">{{ MODE_HELP[mode] }}</p>

        <div v-if="mode === 'custom'" class="space-y-2 pt-1">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-foreground">Tools</span>
            <Button variant="outline" size="sm" @click="addTool">
              <Plus /> Add tool
            </Button>
          </div>

          <p v-if="!tools.length" class="text-xs text-muted-foreground">
            No tools configured — this repo will run no analyzers. Add one, or switch to Auto.
          </p>

          <div
            v-for="(t, i) in tools"
            :key="i"
            class="grid gap-2 sm:grid-cols-[10rem_1fr_1fr_auto] sm:items-center"
          >
            <Select v-model="t.tool">
              <SelectTrigger class="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="o in TOOL_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</SelectItem>
              </SelectContent>
            </Select>
            <Input v-model="t.argsText" placeholder="args (e.g. --config p/ci)" />
            <Input v-model="t.pathsText" placeholder="paths (e.g. back_end/)" />
            <Button
              variant="ghost"
              size="sm"
              title="Remove tool"
              @click="removeTool(i)"
            >
              <Trash2 class="text-muted-foreground" />
            </Button>
          </div>

          <p v-if="tools.length" class="text-xs text-muted-foreground">
            Args and paths are space-separated; leave paths empty to scan the whole repo.
          </p>
        </div>
      </div>
    </CardContent>
  </Card>
</template>
