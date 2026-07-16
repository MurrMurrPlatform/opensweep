<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  CheckCircle2,
  GitCommitHorizontal,
  HandMetal,
  RotateCcw,
  Scale,
  ShieldCheck,
  Ticket,
} from 'lucide-vue-next'
import { useDeliveryStore } from '@/stores/deliveryStore'
import { useToast } from '@/composables/useToast'
import { ApiError } from '@/services/api'
import { Badge, type BadgeVariants } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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
import type { BlockingOverrideValue, FindingResolutionDTO, ResolutionState, Severity } from '@/types/api'

interface Props {
  resolution: FindingResolutionDTO
  /** Render a scope checkbox (fix-run pre-selection on the PR detail page). */
  selectable?: boolean
  selected?: boolean
}
const props = withDefaults(defineProps<Props>(), { selectable: false, selected: false })
const emit = defineEmits<{ updated: [resolution: FindingResolutionDTO]; select: [value: boolean] }>()

const delivery = useDeliveryStore()
const toast = useToast()

const busy = ref<string | null>(null)
const dialog = ref<null | 'attach-fix' | 'verify' | 'waive' | 'override'>(null)
const shaInput = ref('')
const reasonInput = ref('')
const overrideValue = ref<BlockingOverrideValue>('')
const confirmAction = ref<null | 'defer' | 'reopen'>(null)

// Mirrors the backend state machine (resolution_service.py).
const FIXABLE: ResolutionState[] = ['open', 'in-fix', 'reopened']
const TRIAGEABLE: ResolutionState[] = ['open', 'in-fix', 'fixed', 'reopened']

const canAttachFix = computed(() => FIXABLE.includes(props.resolution.state))
const canVerify = computed(() => props.resolution.state === 'fixed')
const canWaive = computed(() => TRIAGEABLE.includes(props.resolution.state))
const canDefer = computed(() => TRIAGEABLE.includes(props.resolution.state))
const canReopen = computed(() => !['open', 'reopened'].includes(props.resolution.state))

const severityVariant = (sev: Severity): BadgeVariants['variant'] => {
  if (sev === 'critical' || sev === 'high') return 'destructive'
  if (sev === 'medium') return 'warn'
  return 'default'
}

const stateVariant = computed<BadgeVariants['variant']>(() => {
  switch (props.resolution.state) {
    case 'verified':
      return 'success' as const
    case 'fixed':
    case 'in-fix':
      return 'info' as const
    case 'open':
    case 'reopened':
      return 'warn' as const
    case 'refuted':
      // Machine-disproved by a verification run — parked, never blocks.
      return 'outline' as const
    default:
      return 'default' as const
  }
})

const shaValid = computed(() => shaInput.value.trim().length >= 7)
const reasonValid = computed(() => reasonInput.value.trim().length >= 5)

function openDialog(kind: 'attach-fix' | 'verify' | 'waive' | 'override') {
  shaInput.value = ''
  reasonInput.value = kind === 'override' ? props.resolution.blocking_override_reason : ''
  overrideValue.value = kind === 'override' ? props.resolution.blocking_override : ''
  dialog.value = kind
}

async function run(action: string, fn: () => Promise<FindingResolutionDTO>, successTitle: string) {
  if (busy.value) return
  busy.value = action
  try {
    const updated = await fn()
    emit('updated', updated)
    dialog.value = null
    toast.success(successTitle, props.resolution.finding_title)
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e)
    toast.error('Action failed', msg)
  } finally {
    busy.value = null
  }
}

function attachFix() {
  if (!shaValid.value) return
  void run('attach-fix', () => delivery.attachFix(props.resolution.uid, shaInput.value.trim()), 'Fix attached')
}

function verify() {
  if (!shaValid.value) return
  void run('verify', () => delivery.verifyResolution(props.resolution.uid, shaInput.value.trim()), 'Verified')
}

function waive() {
  if (!reasonValid.value) return
  void run('waive', () => delivery.waiveResolution(props.resolution.uid, reasonInput.value.trim()), 'Waived')
}

function defer() {
  confirmAction.value = 'defer'
}

function confirmDefer() {
  confirmAction.value = null
  void run('defer', () => delivery.deferResolution(props.resolution.uid), 'Deferred to ticket')
}

function reopen() {
  confirmAction.value = 'reopen'
}

function confirmReopen() {
  confirmAction.value = null
  void run('reopen', () => delivery.reopenResolution(props.resolution.uid), 'Reopened')
}

function applyOverride() {
  if (!reasonValid.value) return
  void run(
    'override',
    () => delivery.setBlockingOverride(props.resolution.uid, overrideValue.value, reasonInput.value.trim()),
    'Override applied',
  )
}

// reka SelectItem values can't be empty strings — use a sentinel for the
// "policy default (clear override)" choice and translate at the boundary.
const OVERRIDE_DEFAULT = '__default__'
const OVERRIDE_OPTIONS = [
  { label: 'Policy default (clear override)', value: OVERRIDE_DEFAULT },
  { label: 'Allow — not important, never blocks', value: 'allow' },
  { label: 'Block — escalate, always blocks', value: 'block' },
]

const overrideSelect = computed({
  get: () => (overrideValue.value === '' ? OVERRIDE_DEFAULT : overrideValue.value),
  set: (v: string) => {
    overrideValue.value = (v === OVERRIDE_DEFAULT ? '' : v) as BlockingOverrideValue
  },
})
</script>

<template>
  <div class="p-4 space-y-2" :class="resolution.waive_requested_reason ? 'bg-warn/5' : ''">
    <div class="flex flex-wrap items-center gap-1.5">
      <input
        v-if="selectable"
        type="checkbox"
        class="h-4 w-4 accent-primary cursor-pointer"
        title="Scope the next fix run to this finding"
        :checked="selected"
        @change="emit('select', ($event.target as HTMLInputElement).checked)"
      />
      <Badge v-if="resolution.blocking" variant="destructive" class="px-1.5 text-[10px]">blocking</Badge>
      <Badge :variant="severityVariant(resolution.finding_severity)" class="px-1.5 text-[10px]">
        {{ resolution.finding_severity }}
      </Badge>
      <Badge v-for="t in resolution.finding_tags || []" :key="t" variant="outline" class="px-1.5 text-[10px]">{{ t }}</Badge>
      <Badge :variant="stateVariant" class="px-1.5 text-[10px]">{{ resolution.state }}</Badge>
      <Badge v-if="resolution.blocking_override" variant="outline" class="px-1.5 text-[10px]">
        <Scale class="h-3 w-3" /> override: {{ resolution.blocking_override }}
      </Badge>
    </div>

    <RouterLink
      :to="{ name: 'finding-detail', params: { uid: resolution.finding_uid } }"
      class="block font-medium text-sm hover:text-primary transition-colors"
    >
      {{ resolution.finding_title || `Finding ${resolution.finding_uid.slice(0, 8)}` }}
    </RouterLink>

    <div
      v-if="resolution.waive_requested_reason"
      class="text-xs text-warn rounded-sm border border-warn/30 bg-warn/10 px-2.5 py-1.5"
    >
      <span class="font-medium">Waiver requested</span>
      <span v-if="resolution.waive_requested_by"> by {{ resolution.waive_requested_by }}</span>:
      {{ resolution.waive_requested_reason }}
    </div>

    <div class="text-xs text-muted-foreground font-mono space-x-2">
      <span v-if="resolution.introduced_at_sha">introduced @{{ resolution.introduced_at_sha.slice(0, 10) }}</span>
      <span v-if="resolution.fixed_at_sha">· fixed @{{ resolution.fixed_at_sha.slice(0, 10) }}</span>
      <span v-if="resolution.verified_at_sha">· verified @{{ resolution.verified_at_sha.slice(0, 10) }}</span>
      <span v-if="resolution.ticket_uid">· ticket {{ resolution.ticket_uid.slice(0, 8) }}</span>
    </div>
    <div v-if="resolution.state === 'waived' && resolution.waive_reason" class="text-xs text-muted-foreground">
      Waived<span v-if="resolution.waived_by"> by {{ resolution.waived_by }}</span>: {{ resolution.waive_reason }}
    </div>
    <div v-if="resolution.state === 'refuted'" class="text-xs text-muted-foreground">
      Refuted by a verification run — the claimed failure could not occur at the reviewed
      commit; the finding was dismissed and no longer blocks.
    </div>
    <div v-if="resolution.blocking_override_reason" class="text-xs text-muted-foreground">
      Override reason: {{ resolution.blocking_override_reason }}
    </div>

    <div class="flex flex-wrap items-center gap-1.5 pt-1">
      <Button variant="outline" size="sm" :disabled="!canAttachFix || !!busy" @click="openDialog('attach-fix')">
        <GitCommitHorizontal /> Attach fix
      </Button>
      <Button variant="outline" size="sm" :disabled="!canVerify || !!busy" @click="openDialog('verify')">
        <ShieldCheck /> Verify
      </Button>
      <Button
        variant="outline"
        size="sm"
        :disabled="!canWaive || !!busy"
        :loading="busy === 'waive' && !dialog"
        @click="openDialog('waive')"
      >
        <HandMetal /> Waive
      </Button>
      <Button variant="outline" size="sm" :disabled="!canDefer || !!busy" :loading="busy === 'defer'" @click="defer">
        <Ticket /> Later → ticket
      </Button>
      <Button variant="outline" size="sm" :disabled="!canReopen || !!busy" :loading="busy === 'reopen'" @click="reopen">
        <RotateCcw /> Reopen
      </Button>
      <Button variant="outline" size="sm" :disabled="!!busy" @click="openDialog('override')">
        <Scale /> Not important / Escalate
      </Button>
    </div>

    <!-- Attach fix -->
    <Dialog :open="dialog === 'attach-fix'" @update:open="dialog = null">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Attach fix</DialogTitle>
          <DialogDescription>
            Claim a fix for this finding at a commit SHA. Only a review at that SHA or later can verify it.
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-1">
          <Label>Fix commit SHA</Label>
          <Input v-model="shaInput" placeholder="at least 7 characters" class="font-mono" @keydown.enter="attachFix" />
        </div>
        <DialogFooter>
          <Button variant="ghost" size="sm" @click="dialog = null">Cancel</Button>
          <Button size="sm" :disabled="!shaValid" :loading="busy === 'attach-fix'" @click="attachFix">
            Attach fix
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Verify -->
    <Dialog :open="dialog === 'verify'" @update:open="dialog = null">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Verify resolution</DialogTitle>
          <DialogDescription>
            Grant verification at a commit SHA — “fixed is claimed, verified is granted”.
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-1">
          <Label>Verified-at commit SHA</Label>
          <Input v-model="shaInput" placeholder="at least 7 characters" class="font-mono" @keydown.enter="verify" />
        </div>
        <DialogFooter>
          <Button variant="ghost" size="sm" @click="dialog = null">Cancel</Button>
          <Button size="sm" :disabled="!shaValid" :loading="busy === 'verify'" @click="verify">
            <CheckCircle2 /> Verify
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Waive -->
    <Dialog :open="dialog === 'waive'" @update:open="dialog = null">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Waive finding</DialogTitle>
          <DialogDescription>
            Waive once, suppress forever: the reason is stored against the dedupe key so re-discovery is auto-suppressed.
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-1">
          <Label>Reason (required, min 5 characters)</Label>
          <Textarea v-model="reasonInput" :rows="3" placeholder="Why is this acceptable to leave unfixed?" />
        </div>
        <DialogFooter>
          <Button variant="ghost" size="sm" @click="dialog = null">Cancel</Button>
          <Button variant="destructive" size="sm" :disabled="!reasonValid" :loading="busy === 'waive'" @click="waive">
            Waive finding
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Blocking override -->
    <Dialog :open="dialog === 'override'" @update:open="dialog = null">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Blocking override</DialogTitle>
          <DialogDescription>
            Override the computed blocking status. Always with a reason, always audited.
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-3">
          <div class="space-y-1">
            <Label>Override</Label>
            <Select v-model="overrideSelect">
              <SelectTrigger class="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="o in OVERRIDE_OPTIONS" :key="o.value" :value="o.value">
                  {{ o.label }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-1">
            <Label>Reason (required, min 5 characters)</Label>
            <Textarea v-model="reasonInput" :rows="3" placeholder="Why override the merge policy for this finding?" />
          </div>
        </div>
        <DialogFooter>
          <Button size="sm" :disabled="!reasonValid" :loading="busy === 'override'" @click="applyOverride">
            Apply override
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Defer confirm -->
    <AlertDialog
      :open="confirmAction === 'defer'"
      @update:open="(v) => { if (!v) confirmAction = null }"
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Defer finding</AlertDialogTitle>
          <AlertDialogDescription>
            Defer “{{ resolution.finding_title }}”? A linked ticket is created and it drops out of the blocking set.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction @click="confirmDefer">Defer</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <!-- Reopen confirm -->
    <AlertDialog
      :open="confirmAction === 'reopen'"
      @update:open="(v) => { if (!v) confirmAction = null }"
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Reopen finding</AlertDialogTitle>
          <AlertDialogDescription>
            Reopen “{{ resolution.finding_title }}”? It re-enters the ledger and may block again.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction @click="confirmReopen">Reopen</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
