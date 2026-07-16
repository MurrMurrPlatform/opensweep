<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import type { LLMProvider, LLMProviderKind, LLMProviderKindMeta } from '@/types/api'

const props = defineProps<{
  open: boolean
  provider?: LLMProvider | null
  catalog: LLMProviderKindMeta[]
  submitting?: boolean
}>()
const emit = defineEmits<{
  'update:open': [v: boolean]
  submit: [value: Partial<LLMProvider>]
}>()

const form = reactive({
  label: '',
  kind: 'claude_subscription' as LLMProviderKind,
  base_url: '',
  model: '',
  api_key_env: '',
  cli_command_template: '',
  extra_args: '',
  enabled: true,
  active: false,
  notes: '',
  credential_secret: '',          // write-only; never pre-filled even when editing
  clear_credential: false,         // explicit "remove the stored secret" toggle
})

function reset() {
  form.label = ''
  form.kind = 'claude_subscription'
  form.base_url = ''
  form.model = ''
  form.api_key_env = ''
  form.cli_command_template = ''
  form.extra_args = ''
  form.enabled = true
  form.active = false
  form.notes = ''
  form.credential_secret = ''
  form.clear_credential = false
}

const currentMeta = computed(() => props.catalog.find(c => c.kind === form.kind))

watch(() => props.open, (val) => {
  if (!val) return
  if (props.provider) {
    const p = props.provider
    form.label = p.label
    form.kind = p.kind
    form.base_url = p.base_url || ''
    form.model = p.model || ''
    form.api_key_env = p.api_key_env || ''
    form.cli_command_template = p.cli_command_template || ''
    form.extra_args = p.extra_args || ''
    form.enabled = p.enabled
    form.active = p.active
    form.notes = p.notes || ''
    form.credential_secret = ''       // never round-trip the stored secret
    form.clear_credential = false
  } else {
    reset()
  }
})

watch(() => form.kind, (val) => {
  // When the user picks a kind, prefill the fields the kind expects.
  const meta = props.catalog.find(c => c.kind === val)
  if (!meta) return
  if (!form.cli_command_template && meta.default_cli) form.cli_command_template = meta.default_cli
  if (!form.model && meta.default_model) form.model = meta.default_model
})

const kindOptions = computed(() =>
  props.catalog.map(c => ({ value: c.kind, label: `${c.display_name}` })),
)

// Literal strings — keep nested mustaches out of the template parser.
const placeholderInstruction = '{{instruction_q}}'
const placeholderSystemPrompt = '{{system_prompt_q}}'
const placeholderModel = '{{model}}'

function onSubmit() {
  const payload: Record<string, unknown> = {
    label: form.label,
    kind: form.kind,
    base_url: form.base_url,
    model: form.model,
    api_key_env: form.api_key_env,
    cli_command_template: form.cli_command_template,
    extra_args: form.extra_args,
    enabled: form.enabled,
    active: form.active,
    notes: form.notes,
  }
  // Only send credential_secret if the user typed something OR asked to clear.
  if (form.credential_secret) {
    payload.credential_secret = form.credential_secret
  } else if (form.clear_credential) {
    payload.credential_secret = ''
  }
  emit('submit', payload as Partial<LLMProvider>)
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="sm:max-w-lg">
      <DialogHeader>
        <DialogTitle>{{ provider ? `Edit provider · ${provider.label}` : 'Add LLM provider' }}</DialogTitle>
        <DialogDescription>
          Configure where this provider runs (CLI, hosted API, or local server).
        </DialogDescription>
      </DialogHeader>

      <div class="flex flex-col gap-3 max-h-[60vh] overflow-y-auto -mx-6 px-6">
        <div class="flex flex-col gap-1.5">
          <Label for="provider-label">Label</Label>
          <Input id="provider-label" v-model="form.label" placeholder="e.g. Claude (subscription)" />
        </div>

        <div class="flex flex-col gap-1.5">
          <Label for="provider-kind">Kind</Label>
          <Select
            :model-value="form.kind"
            @update:model-value="form.kind = $event as LLMProviderKind"
          >
            <SelectTrigger id="provider-kind" class="w-full">
              <SelectValue placeholder="Select a kind" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="o in kindOptions" :key="o.value" :value="o.value">
                {{ o.label }}
              </SelectItem>
            </SelectContent>
          </Select>
          <span v-if="currentMeta" class="text-muted-foreground text-xs">{{ currentMeta.transport }}</span>
        </div>

        <div class="flex flex-col gap-1.5">
          <Label for="provider-model">Model</Label>
          <Input id="provider-model" v-model="form.model" placeholder="model id (eg claude-opus-4-7)" />
        </div>

        <div v-if="currentMeta?.needs_base_url" class="flex flex-col gap-1.5">
          <Label for="provider-base-url">Base URL</Label>
          <Input id="provider-base-url" v-model="form.base_url" placeholder="http://host.docker.internal:1234/v1" />
        </div>

        <div v-if="currentMeta?.needs_api_key" class="flex flex-col gap-1.5">
          <Label for="provider-api-key-env">API-key env var</Label>
          <Input id="provider-api-key-env" v-model="form.api_key_env" placeholder="ANTHROPIC_API_KEY" />
          <span class="text-muted-foreground text-xs">Fallback if you don't paste the key in 'Credential' below.</span>
        </div>

        <!-- Credential section — kind-aware. -->
        <div v-if="currentMeta?.needs_credential" class="rounded-md border bg-muted p-3 flex flex-col gap-2">
          <div class="flex items-center justify-between">
            <span class="font-semibold text-sm">{{ currentMeta.credential_label || 'Credential' }}</span>
            <span class="text-xs flex items-center gap-2">
              <span
                :class="(provider?.has_credential_secret && !form.clear_credential) ? 'text-good' : 'text-muted-foreground'"
              >
                {{ (provider?.has_credential_secret && !form.clear_credential) ? '✓ set' : 'not set' }}
              </span>
              <button
                v-if="provider?.has_credential_secret"
                type="button"
                class="text-destructive underline"
                @click="form.clear_credential = !form.clear_credential; if (form.clear_credential) form.credential_secret = ''"
              >
                {{ form.clear_credential ? 'undo clear' : 'clear' }}
              </button>
            </span>
          </div>

          <Textarea
            v-model="form.credential_secret"
            :placeholder="provider?.has_credential_secret ? '— leave blank to keep current value —' : currentMeta.credential_placeholder"
            :rows="form.kind === 'codex_subscription' ? 6 : 2"
            class="font-mono text-xs"
          />

          <details v-if="currentMeta.setup_steps?.length" class="text-xs text-muted-foreground">
            <summary class="cursor-pointer hover:text-foreground">How to get this</summary>
            <ol class="mt-2 list-decimal pl-5 space-y-1">
              <li v-for="(step, i) in currentMeta.setup_steps" :key="i">{{ step }}</li>
            </ol>
          </details>
        </div>

        <div v-if="currentMeta && currentMeta.transport === 'local CLI'" class="flex flex-col gap-1.5">
          <Label for="provider-cli">CLI command template</Label>
          <Textarea id="provider-cli" v-model="form.cli_command_template" :rows="2" class="font-mono" />
          <span class="text-muted-foreground text-xs">
            Placeholders: <code>{{ placeholderInstruction }}</code>, <code>{{ placeholderSystemPrompt }}</code>, <code>{{ placeholderModel }}</code>.
            The <code>_q</code> variants are shell-quoted.
          </span>
        </div>

        <div class="flex flex-col gap-1.5">
          <Label for="provider-extra-args">Extra args (appended verbatim)</Label>
          <Input id="provider-extra-args" v-model="form.extra_args" placeholder="" />
        </div>

        <div class="flex flex-col gap-1.5">
          <Label for="provider-notes">Notes</Label>
          <Textarea id="provider-notes" v-model="form.notes" :rows="2" />
        </div>

        <div class="flex items-center justify-between border rounded-md px-3 py-2 text-sm">
          <span>Enabled</span>
          <Switch v-model="form.enabled" />
        </div>

        <div class="flex items-center justify-between border rounded-md px-3 py-2 text-sm">
          <div>
            <div>Active provider</div>
            <div class="text-xs text-muted-foreground">Normal investigations use this provider automatically.</div>
          </div>
          <Switch v-model="form.active" />
        </div>
      </div>

      <DialogFooter>
        <Button variant="ghost" @click="emit('update:open', false)">Cancel</Button>
        <Button :disabled="!form.label.trim() || submitting" :loading="submitting" @click="onSubmit">
          {{ provider ? 'Save changes' : 'Add provider' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
