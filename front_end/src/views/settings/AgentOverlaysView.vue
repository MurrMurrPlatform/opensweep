<script setup lang="ts">
// Org settings → Agents: per-playbook overlays on the platform task
// instructions (spec: docs/superpowers/specs/2026-07-14-org-agent-overlays-design.md).
// Structural framing (identity, tool contract, look-before-write) is code and
// never editable here — orgs tune only the task-instructions layer.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Bot, ChevronDown, Eye, History, Pencil, RotateCcw, Save, TriangleAlert, Undo2, X,
} from 'lucide-vue-next'
import {
  useAgentOverlayStore,
  type AgentOverlayDTO,
  type OverlayMode,
  type OverlayRevisionDTO,
  type PlaybookOverlayStatusDTO,
} from '@/stores/agentOverlayStore'
import { useOrganizationStore } from '@/stores/organizationStore'
import { useToast } from '@/composables/useToast'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
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
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'

const store = useAgentOverlayStore()
const org = useOrganizationStore()
const toast = useToast()

/** Backend body cap (bytes); mirrored client-side as a soft character count. */
const BODY_CAP = 32 * 1024

/** Short human description per playbook — order comes from the API. */
const PLAYBOOK_DESCRIPTIONS: Record<string, string> = {
  chat: 'Conversational agent behind @opensweep mentions and the chat widget.',
  ask: 'Answers questions and runs audits across a workspace.',
  review: 'Reviews pull requests and files findings.',
  fix: 'Fixes a finding with a focused code change.',
  implement: 'Implements a ticket end to end.',
  verify: 'Verifies delivered changes against their intent.',
  document: 'Writes and refreshes workspace documentation.',
  refine: 'Triages a finding or ticket and sharpens it in place.',
  'deep-scan': 'Deep-scans the whole repository and authors a full Analysis report.',
  'generate-docs': 'Proposes and rebuilds the documentation page tree.',
}

const loading = ref(true)

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([
      store.fetchAll(),
      // Resolve `updated_by` / `author_uid` to member emails; never blocks.
      org.fetchMembers().catch(() => {}),
    ])
  } catch (e: any) {
    toast.error('Load failed', e.detail || e.message)
  } finally {
    loading.value = false
  }
})

function memberLabel(uid: string): string {
  if (!uid) return 'unknown'
  const m = org.members.find((x) => x.uid === uid)
  return m?.email || m?.display_name || uid
}

function formatWhen(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function titleCase(playbook: string): string {
  // Hyphenated agent keys ("deep-scan") render as words ("Deep scan").
  const words = playbook.replace(/-/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

// ── Editor ─────────────────────────────────────────────────────────────────
const editing = ref<string | null>(null)
const draftMode = ref<OverlayMode>('append')
const draftBody = ref('')
const draftEnabled = ref(true)
const saving = ref(false)
/** 422 (body cap / bad mode) surfaced inline next to Save, not just a toast. */
const saveError = ref('')

const bodyTooLong = computed(() => draftBody.value.length > BODY_CAP)

function startEdit(entry: PlaybookOverlayStatusDTO) {
  editing.value = entry.playbook
  draftMode.value = entry.overlay?.mode ?? 'append'
  draftBody.value = entry.overlay?.body ?? ''
  draftEnabled.value = entry.overlay?.enabled ?? true
  saveError.value = ''
  closePreview()
}

function cancelEdit() {
  editing.value = null
  saveError.value = ''
  closePreview()
}

async function saveEdit(playbook: string) {
  if (saving.value) return
  saving.value = true
  saveError.value = ''
  try {
    await store.upsert(playbook, {
      mode: draftMode.value,
      body: draftBody.value,
      enabled: draftEnabled.value,
    })
    toast.success('Overlay saved', titleCase(playbook))
    editing.value = null
    closePreview()
  } catch (e: any) {
    // 422 = bad mode or body over the 32 KB cap — backend detail says which.
    saveError.value = e.detail || e.message
    toast.error('Save failed', e.detail || e.message)
  } finally {
    saving.value = false
  }
}

// ── Restore platform default ───────────────────────────────────────────────
const restoreTarget = ref<string | null>(null)
const restoring = ref(false)

async function confirmRestore() {
  const playbook = restoreTarget.value
  if (!playbook) return
  restoring.value = true
  try {
    await store.restoreDefault(playbook)
    toast.success('Platform default restored', titleCase(playbook))
    if (editing.value === playbook) cancelEdit()
    restoreTarget.value = null
  } catch (e: any) {
    toast.error('Restore failed', e.detail || e.message)
  } finally {
    restoring.value = false
  }
}

// ── Composed-prompt preview ────────────────────────────────────────────────
const previewOpen = ref(false)
const previewText = ref('')
const previewLoading = ref(false)
const previewError = ref('')
let previewTimer: ReturnType<typeof setTimeout> | null = null

function closePreview() {
  previewOpen.value = false
  previewText.value = ''
  previewError.value = ''
  if (previewTimer) { clearTimeout(previewTimer); previewTimer = null }
}

async function refreshPreview() {
  const playbook = editing.value
  if (!playbook) return
  previewLoading.value = true
  previewError.value = ''
  try {
    const res = await store.preview(playbook, { mode: draftMode.value, body: draftBody.value })
    previewText.value = res.prompt
  } catch (e: any) {
    // Preview failures are non-blocking — saving stays independent.
    previewError.value = e.detail || e.message
  } finally {
    previewLoading.value = false
  }
}

function togglePreview() {
  if (previewOpen.value) { closePreview(); return }
  previewOpen.value = true
  void refreshPreview()
}

// Live preview: re-compose the draft (debounced) while the pane is open.
watch([draftMode, draftBody], () => {
  if (!previewOpen.value || !editing.value) return
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(() => void refreshPreview(), 600)
})

onBeforeUnmount(() => { if (previewTimer) clearTimeout(previewTimer) })

// ── History drawer ─────────────────────────────────────────────────────────
const historyPlaybook = ref<string | null>(null)
const revisions = ref<OverlayRevisionDTO[]>([])
const historyLoading = ref(false)
const revertTarget = ref<OverlayRevisionDTO | null>(null)
const reverting = ref(false)

async function openHistory(playbook: string) {
  historyPlaybook.value = playbook
  historyLoading.value = true
  revisions.value = []
  try {
    revisions.value = await store.fetchRevisions(playbook)
  } catch (e: any) {
    toast.error('History failed', e.detail || e.message)
  } finally {
    historyLoading.value = false
  }
}

async function confirmRevert() {
  const target = revertTarget.value
  const playbook = historyPlaybook.value
  if (!target || !playbook) return
  reverting.value = true
  try {
    const overlay: AgentOverlayDTO = await store.revert(playbook, target.rev)
    toast.success('Reverted', `${titleCase(playbook)} → revision ${target.rev} (new head r${overlay.rev})`)
    revertTarget.value = null
    // Refresh the drawer — revert appends a new head revision.
    revisions.value = await store.fetchRevisions(playbook)
    if (editing.value === playbook) {
      draftMode.value = overlay.mode
      draftBody.value = overlay.body
      draftEnabled.value = overlay.enabled
    }
  } catch (e: any) {
    toast.error('Revert failed', e.detail || e.message)
  } finally {
    reverting.value = false
  }
}
</script>

<template>
  <div class="space-y-4 max-w-4xl">
    <PageHeader
      title="Agents"
      subtitle="Tune how OpenSweep's agents behave for your organization. Your guidance layers on top of the platform instructions — structure and safety framing stay platform-owned."
    />

    <div v-if="loading" class="space-y-3">
      <Skeleton v-for="i in 4" :key="i" class="h-28" />
    </div>

    <div v-else class="stagger-children space-y-3">
      <Card v-for="entry in store.entries" :key="entry.playbook">
        <CardContent class="space-y-3 p-4">
          <!-- Row header: name, status badges, actions -->
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <Bot class="h-4 w-4 text-muted-foreground shrink-0" />
                <span class="text-sm font-semibold">{{ titleCase(entry.playbook) }}</span>
                <Badge v-if="entry.overlay && entry.overlay.enabled" variant="info" class="px-1.5 text-[10px]">
                  customized
                </Badge>
                <Badge v-else-if="entry.overlay" variant="outline" class="px-1.5 text-[10px]">
                  overlay off
                </Badge>
                <!-- Persistent drift flag: replace-mode overlays discard the platform layer. -->
                <Badge v-if="entry.overlay?.mode === 'replace'" variant="warn" class="px-1.5 text-[10px]">
                  <TriangleAlert class="h-3 w-3" /> replaces platform instructions
                </Badge>
              </div>
              <p class="mt-0.5 text-xs text-muted-foreground">
                {{ PLAYBOOK_DESCRIPTIONS[entry.playbook] || 'OpenSweep agent playbook.' }}
              </p>
              <!-- Governance: any member can edit, so attribution is prominent. -->
              <p v-if="entry.overlay" class="mt-1 text-xs font-medium text-foreground/80">
                Last edited by {{ memberLabel(entry.overlay.updated_by) }}
                · {{ formatWhen(entry.overlay.updated_at) }}
                · revision {{ entry.overlay.rev }}
              </p>
            </div>
            <div class="flex shrink-0 flex-wrap items-center gap-1.5">
              <Button variant="ghost" size="sm" @click="openHistory(entry.playbook)">
                <History /> History
              </Button>
              <Button
                v-if="entry.overlay"
                variant="ghost"
                size="sm"
                class="text-destructive"
                @click="restoreTarget = entry.playbook"
              >
                <RotateCcw /> Restore default
              </Button>
              <Button
                v-if="editing !== entry.playbook"
                variant="outline"
                size="sm"
                @click="startEdit(entry)"
              >
                <Pencil /> {{ entry.overlay ? 'Edit overlay' : 'Customize' }}
              </Button>
              <Button v-else variant="outline" size="sm" @click="cancelEdit">
                <X /> Close
              </Button>
            </div>
          </div>

          <!-- Platform instructions (read-only, collapsible) -->
          <Collapsible v-if="entry.platform" v-slot="{ open }">
            <CollapsibleTrigger
              class="flex w-full items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              <ChevronDown :class="['h-3.5 w-3.5 transition-transform', open ? '' : '-rotate-90']" />
              Platform instructions
              <span class="text-[10px] font-normal">(read-only)</span>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <pre class="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-md border bg-muted/40 p-3 font-mono text-xs text-muted-foreground">{{ entry.platform.body }}</pre>
            </CollapsibleContent>
          </Collapsible>
          <p v-else class="text-xs text-muted-foreground">
            No platform base seeded for this playbook — the built-in default instructions apply.
          </p>

          <!-- Overlay editor -->
          <div v-if="editing === entry.playbook" class="space-y-3 rounded-md border bg-muted/20 p-3">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <!-- Mode toggle: append (default) vs replace (flagged) -->
              <div class="inline-flex rounded-md border p-0.5">
                <button
                  type="button"
                  :class="[
                    'rounded px-3 py-1 text-xs font-medium transition-colors',
                    draftMode === 'append' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
                  ]"
                  @click="draftMode = 'append'"
                >
                  Append
                </button>
                <button
                  type="button"
                  :class="[
                    'flex items-center gap-1 rounded px-3 py-1 text-xs font-medium transition-colors',
                    draftMode === 'replace' ? 'bg-warn/20 text-warn' : 'text-muted-foreground hover:text-foreground',
                  ]"
                  @click="draftMode = 'replace'"
                >
                  <TriangleAlert class="h-3 w-3" /> Replace
                </button>
              </div>
              <label class="flex items-center gap-2 text-xs">
                <Switch v-model="draftEnabled" />
                <span :class="draftEnabled ? 'text-foreground' : 'text-muted-foreground'">
                  {{ draftEnabled ? 'Overlay enabled' : 'Overlay disabled — platform default runs' }}
                </span>
              </label>
            </div>

            <div
              v-if="draftMode === 'replace'"
              class="flex items-start gap-2 rounded-md border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-warn"
            >
              <TriangleAlert class="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                Replace mode discards the platform instructions for this agent entirely — your text
                below becomes its task instructions. Structural framing and repo guidance still apply.
                "Restore default" brings the platform version back at any time.
              </span>
            </div>
            <p v-else class="text-xs text-muted-foreground">
              Your guidance is appended under the platform instructions as an
              "Organization guidance" section.
            </p>

            <div class="space-y-1.5">
              <Label :for="`overlay-body-${entry.playbook}`" class="text-xs uppercase text-muted-foreground">
                Organization guidance (markdown)
              </Label>
              <Textarea
                :id="`overlay-body-${entry.playbook}`"
                v-model="draftBody"
                :placeholder="`e.g. Always answer in English. Prefer small, reviewable diffs. Follow our ADRs under docs/adr/.`"
                class="min-h-40 font-mono text-xs"
              />
              <div :class="['text-right text-[10px]', bodyTooLong ? 'font-medium text-destructive' : 'text-muted-foreground']">
                {{ draftBody.length.toLocaleString() }} / {{ BODY_CAP.toLocaleString() }} characters
              </div>
            </div>

            <p v-if="saveError" class="text-xs font-medium text-destructive">{{ saveError }}</p>

            <div class="flex flex-wrap items-center gap-2">
              <Button size="sm" :loading="saving" :disabled="bodyTooLong" @click="saveEdit(entry.playbook)">
                <Save /> Save overlay
              </Button>
              <Button size="sm" variant="ghost" @click="cancelEdit">Cancel</Button>
              <Button size="sm" variant="outline" class="ml-auto" @click="togglePreview">
                <Eye /> {{ previewOpen ? 'Hide preview' : 'Preview composed prompt' }}
              </Button>
            </div>

            <!-- Composed-prompt preview: exactly what the agent receives for this draft. -->
            <div v-if="previewOpen" class="space-y-1.5">
              <div class="flex items-center justify-between">
                <span class="text-xs uppercase text-muted-foreground">Composed prompt (draft, read-only)</span>
                <Button size="sm" variant="ghost" :loading="previewLoading" @click="refreshPreview">
                  Refresh
                </Button>
              </div>
              <p v-if="previewError" class="text-xs text-warn">
                Preview unavailable: {{ previewError }} — saving still works.
              </p>
              <Skeleton v-else-if="previewLoading && !previewText" class="h-40" />
              <pre
                v-else
                class="max-h-96 overflow-y-auto whitespace-pre-wrap rounded-md border bg-background p-3 font-mono text-xs"
              >{{ previewText }}</pre>
            </div>
          </div>

          <!-- Collapsed overlay summary (not editing) -->
          <div v-else-if="entry.overlay" class="rounded-md border bg-muted/20 p-3">
            <div class="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
              <span class="uppercase">Organization overlay</span>
              <Badge :variant="entry.overlay.mode === 'replace' ? 'warn' : 'secondary'" class="px-1.5 text-[10px]">
                {{ entry.overlay.mode }}
              </Badge>
            </div>
            <pre class="max-h-40 overflow-y-auto whitespace-pre-wrap font-mono text-xs">{{ entry.overlay.body || '(empty)' }}</pre>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- Restore-default confirm -->
    <AlertDialog :open="restoreTarget !== null" @update:open="(v: boolean) => { if (!v) restoreTarget = null }">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Restore platform default</AlertDialogTitle>
          <AlertDialogDescription>
            Remove your organization's overlay for
            <span class="font-medium">{{ restoreTarget ? titleCase(restoreTarget) : '' }}</span>
            and run the platform instructions as-is? Revision history is kept — you can revert later.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            :disabled="restoring"
            @click="confirmRestore"
          >
            <RotateCcw /> Restore default
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <!-- History drawer -->
    <Sheet :open="historyPlaybook !== null" @update:open="(v: boolean) => { if (!v) historyPlaybook = null }">
      <SheetContent side="right" class="flex w-full flex-col sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>
            {{ historyPlaybook ? titleCase(historyPlaybook) : '' }} — overlay history
          </SheetTitle>
          <SheetDescription>
            Every save is a revision. Reverting copies an old revision into a new head — history is never rewritten.
          </SheetDescription>
        </SheetHeader>
        <div class="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          <div v-if="historyLoading" class="space-y-2">
            <Skeleton v-for="i in 3" :key="i" class="h-20" />
          </div>
          <p v-else-if="!revisions.length" class="text-sm text-muted-foreground">
            No revisions yet — this playbook has never been customized.
          </p>
          <template v-else>
          <div
            v-for="(r, idx) in revisions"
            :key="r.uid"
            class="space-y-2 rounded-md border p-3"
          >
            <div class="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant="outline" class="px-1.5 text-[10px]">r{{ r.rev }}</Badge>
              <Badge :variant="r.mode === 'replace' ? 'warn' : 'secondary'" class="px-1.5 text-[10px]">
                {{ r.mode }}
              </Badge>
              <Badge v-if="!r.enabled" variant="outline" class="px-1.5 text-[10px]">disabled</Badge>
              <span class="text-muted-foreground">
                {{ memberLabel(r.author_uid) }} · {{ formatWhen(r.created_at) }}
              </span>
              <Button
                size="sm"
                variant="outline"
                class="ml-auto"
                :disabled="idx === 0"
                @click="revertTarget = r"
              >
                <Undo2 /> Revert
              </Button>
            </div>
            <pre class="max-h-40 overflow-y-auto whitespace-pre-wrap rounded bg-muted/40 p-2 font-mono text-[11px]">{{ r.body || '(empty)' }}</pre>
          </div>
          </template>
        </div>
      </SheetContent>
    </Sheet>

    <!-- Revert confirm -->
    <AlertDialog :open="revertTarget !== null" @update:open="(v: boolean) => { if (!v) revertTarget = null }">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Revert to revision {{ revertTarget?.rev }}</AlertDialogTitle>
          <AlertDialogDescription>
            The overlay for {{ historyPlaybook ? titleCase(historyPlaybook) : '' }} is set back to
            revision {{ revertTarget?.rev }} ({{ revertTarget?.mode }} mode) as a new head revision.
            Nothing is deleted.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction :disabled="reverting" @click="confirmRevert">
            <Undo2 /> Revert
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
