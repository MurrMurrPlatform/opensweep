<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge, type BadgeVariants } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/ui/page-header'
import { EmptyState } from '@/components/ui/empty-state'
import LLMProviderFormDialog from '@/components/llmProviders/LLMProviderFormDialog.vue'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useLLMProviderStore } from '@/stores/llmProviderStore'
import { useCurrentUserStore } from '@/stores/currentUserStore'
import { useToast } from '@/composables/useToast'
import type { LLMProvider } from '@/types/api'
import { Plus, Pencil, Trash2, Activity, Info, Cpu } from 'lucide-vue-next'

const store = useLLMProviderStore()
const currentUser = useCurrentUserStore()
const toast = useToast()
const dialogOpen = ref(false)
const editing = ref<LLMProvider | null>(null)
const submitting = ref(false)
const checking = ref<string | null>(null)
const deleteOpen = ref(false)
const pendingDelete = ref<LLMProvider | null>(null)

onMounted(async () => {
  await Promise.all([store.fetchAll(), store.fetchCatalog()])
})

function openCreate() {
  editing.value = null
  dialogOpen.value = true
}

function openEdit(p: LLMProvider) {
  editing.value = p
  dialogOpen.value = true
}

async function onSubmit(value: Partial<LLMProvider>) {
  submitting.value = true
  try {
    if (editing.value) {
      await store.update(editing.value.uid, value)
      toast.success('Provider updated')
    } else {
      await store.create(value)
      toast.success('Provider added')
    }
    dialogOpen.value = false
  } catch (e: any) {
    toast.error('Save failed', e.detail || e.message)
  } finally {
    submitting.value = false
  }
}

function onDelete(p: LLMProvider) {
  pendingDelete.value = p
  deleteOpen.value = true
}

async function confirmDelete() {
  const p = pendingDelete.value
  if (!p) return
  deleteOpen.value = false
  try {
    await store.remove(p.uid)
    toast.success('Provider deleted')
  } catch (e: any) {
    toast.error('Delete failed', e.detail || e.message)
  }
}

async function onCheck(p: LLMProvider) {
  checking.value = p.uid
  try {
    await store.check(p.uid)
    toast.success('Health check complete')
  } catch (e: any) {
    toast.error('Health check failed', e.detail || e.message)
  } finally {
    checking.value = null
  }
}

async function onSetActive(p: LLMProvider) {
  try {
    await store.setActive(p.uid)
    toast.success('Active provider set', p.label)
  } catch (e: any) {
    toast.error('Activation failed', e.detail || e.message)
  }
}

function healthVariant(status?: string): BadgeVariants['variant'] {
  if (status === 'ok') return 'success'
  if (status === 'degraded') return 'warn'
  if (status === 'unreachable') return 'destructive'
  return 'outline'
}

function kindLabel(kind: string): string {
  const c = store.catalog.find(x => x.kind === kind)
  return c ? c.display_name : kind
}

// Providers are org-owned; writes need the org-admin role. Everyone else is read-only.
function canManage(): boolean {
  return currentUser.isAdmin
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <PageHeader
      title="LLM Providers"
      subtitle="Your organization's providers carry your own credentials. Runs use your active provider automatically, with fallback along the priority chain."
    >
      <Button v-if="currentUser.isAdmin" @click="openCreate">
        <Plus /> Add provider
      </Button>
    </PageHeader>

    <!-- Setup help — collapsible, summarises how to wire each kind. -->
    <details class="rounded-lg border bg-card p-4">
      <summary class="cursor-pointer text-sm font-medium flex items-center gap-2">
        <Info class="h-4 w-4 text-primary" />
        Setup guide — how OpenSweep reaches each provider
      </summary>
      <div class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-muted-foreground">
        <div class="rounded-md bg-muted p-3">
          <div class="font-semibold mb-1">Claude Code (subscription)</div>
          <ol class="list-decimal pl-5 space-y-1 text-xs">
            <li>On your Mac: <code class="font-mono">claude setup-token</code></li>
            <li>Copy the printed token (starts with <code>sk-ant-oat...</code>).</li>
            <li>Edit the provider → paste into the <em>Credential</em> field → Save.</li>
            <li>OpenSweep injects it as <code>CLAUDE_CODE_OAUTH_TOKEN</code> when running <code>claude</code> inside the container — no Keychain, no in-container login.</li>
          </ol>
        </div>

        <div class="rounded-md bg-muted p-3">
          <div class="font-semibold mb-1">OpenAI Codex (subscription)</div>
          <ol class="list-decimal pl-5 space-y-1 text-xs">
            <li>On your Mac: <code class="font-mono">codex login</code> (writes <code>~/.codex/auth.json</code>).</li>
            <li>Default: leave <em>Credential</em> blank — OpenSweep bind-mounts <code>~/.codex/</code> from your host into the container.</li>
            <li>Or override: open <code>~/.codex/auth.json</code>, copy contents, paste into the <em>Credential</em> field. OpenSweep writes a worker-private copy at run-time.</li>
          </ol>
        </div>

        <div class="rounded-md bg-muted p-3">
          <div class="font-semibold mb-1">Anthropic / OpenAI API (per-token billing)</div>
          <ol class="list-decimal pl-5 space-y-1 text-xs">
            <li>Generate an API key in the relevant console.</li>
            <li>Either paste it into <em>Credential</em> (OpenSweep stores it), or set the env var named in <em>API-key env var</em> on the backend container.</li>
            <li>Billed per token — separate from Claude/ChatGPT subscriptions.</li>
          </ol>
        </div>

        <div class="rounded-md bg-muted p-3">
          <div class="font-semibold mb-1">MLX / LMStudio / Ollama (local)</div>
          <ol class="list-decimal pl-5 space-y-1 text-xs">
            <li>Run the server on your host (MLX <code>mlx_lm.server</code>, LMStudio's server tab, <code>ollama serve</code>).</li>
            <li>From Docker, reach it at <code>http://host.docker.internal:&lt;port&gt;/v1</code>.</li>
            <li>Click <em>Check</em> — OpenSweep probes <code>/v1/models</code>.</li>
            <li>Free + private. Best for high-volume autonomous scans.</li>
          </ol>
        </div>
      </div>
    </details>

    <Card>
    <CardHeader>
      <div class="flex items-center justify-between gap-2">
        <CardTitle class="text-base">Connected providers</CardTitle>
        <span class="text-xs text-muted-foreground">{{ store.list.length }}</span>
      </div>
    </CardHeader>
    <CardContent>
      <div v-if="!store.loaded" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        <Skeleton v-for="i in 4" :key="i" class="h-44" />
      </div>
      <EmptyState
        v-else-if="!store.list.length"
        :icon="Cpu"
        title="No providers configured"
        description="Add a provider to route investigations to your LLM of choice."
        class="border-0"
      >
        <Button v-if="currentUser.isAdmin" @click="openCreate">
          <Plus /> Add provider
        </Button>
      </EmptyState>
      <div v-else class="stagger-children grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        <div
          v-for="p in store.list"
          :key="p.uid"
          class="rounded-lg border bg-card p-4 flex flex-col gap-2"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="font-semibold truncate">{{ p.label }}</div>
              <div class="text-muted-foreground text-xs truncate">{{ kindLabel(p.kind) }}</div>
            </div>
            <div class="flex flex-col gap-1 items-end">
              <Badge :variant="p.enabled ? 'success' : 'outline'" class="px-1.5 text-[10px]">
                {{ p.enabled ? 'Enabled' : 'Disabled' }}
              </Badge>
              <Badge :variant="p.active ? 'success' : 'outline'" class="px-1.5 text-[10px]">
                {{ p.active ? 'Active' : 'standby' }}
              </Badge>
              <Badge :variant="healthVariant(p.last_health_status)" class="px-1.5 text-[10px]">
                {{ p.last_health_status }}
              </Badge>
              <Badge :variant="p.has_credential_secret ? 'success' : 'outline'" class="px-1.5 text-[10px]">
                {{ p.has_credential_secret ? '✓ credential' : 'no credential' }}
              </Badge>
            </div>
          </div>

          <div class="text-muted-foreground text-xs space-y-1">
            <div v-if="p.model"><span class="text-muted-foreground">model: </span>{{ p.model }}</div>
            <div v-if="p.base_url"><span class="text-muted-foreground">url: </span><span class="font-mono">{{ p.base_url }}</span></div>
            <div v-if="p.api_key_env"><span class="text-muted-foreground">env: </span><span class="font-mono">{{ p.api_key_env }}</span></div>
            <div v-if="p.cli_command_template" class="font-mono truncate"><span class="text-muted-foreground">cli: </span>{{ p.cli_command_template }}</div>
            <div v-if="p.last_health_detail" class="text-muted-foreground italic">{{ p.last_health_detail }}</div>
          </div>

          <!-- Writes 403 without the org-admin role — read-only card in that case. -->
          <div v-if="canManage()" class="flex flex-wrap items-center gap-2 mt-2">
            <Button size="sm" variant="outline" :loading="checking === p.uid" @click="onCheck(p)">
              <Activity /> Check
            </Button>
            <Button v-if="!p.active" size="sm" variant="outline" @click="onSetActive(p)">
              Set active
            </Button>
            <Button size="sm" variant="ghost" @click="openEdit(p)">
              <Pencil /> Edit
            </Button>
            <Button size="sm" variant="ghost" class="text-destructive" @click="onDelete(p)">
              <Trash2 />
            </Button>
          </div>
        </div>
      </div>
    </CardContent>
    </Card>

    <LLMProviderFormDialog
      v-model:open="dialogOpen"
      :provider="editing"
      :catalog="store.catalog"
      :submitting="submitting"
      @submit="onSubmit"
    />

    <AlertDialog v-model:open="deleteOpen">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete provider</AlertDialogTitle>
          <AlertDialogDescription>
            Delete provider "{{ pendingDelete?.label }}"?
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            @click="confirmDelete"
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
