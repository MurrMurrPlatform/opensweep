<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useTicketStore } from '@/stores/ticketStore'
import { useToast } from '@/composables/useToast'
import { ApiError } from '@/services/api'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { STATUS_LABELS } from '@/components/tickets/ticketMeta'
import type { PullRequestDTO, TicketDTO } from '@/types/api'

interface Props {
  open: boolean
  pr: PullRequestDTO
}
const props = defineProps<Props>()
const emit = defineEmits<{ 'update:open': [value: boolean]; linked: [pr: PullRequestDTO] }>()

const store = useTicketStore()
const toast = useToast()

const candidates = ref<TicketDTO[]>([])
const selectedUid = ref('')
const loading = ref(false)
const loadError = ref<string | null>(null)
const linking = ref(false)

// Implementable tickets for this PR's repository: todo + in-progress.
async function loadCandidates() {
  loading.value = true
  loadError.value = null
  try {
    const [todo, inProgress] = await Promise.all([
      store.listTickets({ repository_uid: props.pr.repository_uid, status: 'todo' }),
      store.listTickets({ repository_uid: props.pr.repository_uid, status: 'in-progress' }),
    ])
    candidates.value = [...todo, ...inProgress]
  } catch (e: unknown) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      selectedUid.value = ''
      void loadCandidates()
    }
  },
)

const options = computed(() =>
  candidates.value.map((t) => ({
    label: `${STATUS_LABELS[t.status]} · ${t.title}`,
    value: t.uid,
  })),
)

const canLink = computed(() => Boolean(selectedUid.value && !linking.value))

async function link() {
  if (!canLink.value) return
  linking.value = true
  try {
    const updated = await store.linkTicketToPullRequest(props.pr.uid, selectedUid.value)
    toast.success('Ticket linked', `#${props.pr.github_number} · ${props.pr.title}`)
    emit('linked', updated)
    emit('update:open', false)
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e)
    toast.error('Link failed', msg)
  } finally {
    linking.value = false
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="sm:max-w-lg">
      <DialogHeader>
        <DialogTitle>Link a ticket</DialogTitle>
        <DialogDescription>
          Bind this PR to the ticket it implements. Only Todo and In-Progress tickets for this
          repository are offered.
        </DialogDescription>
      </DialogHeader>

      <Skeleton v-if="loading" class="h-9" />
      <p v-else-if="loadError" class="text-sm text-destructive">{{ loadError }}</p>
      <p v-else-if="options.length === 0" class="text-sm text-muted-foreground">
        No Todo or In-Progress tickets for this repository. Approve one on the Tickets board first.
      </p>
      <div v-else class="space-y-1.5">
        <Label for="link-ticket">Ticket</Label>
        <Select :model-value="selectedUid" @update:model-value="selectedUid = $event as string">
          <SelectTrigger id="link-ticket" class="w-full">
            <SelectValue placeholder="Select a ticket…" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="o in options" :key="o.value" :value="o.value">{{ o.label }}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <DialogFooter>
        <Button variant="ghost" size="sm" @click="emit('update:open', false)">Cancel</Button>
        <Button size="sm" :disabled="!canLink" :loading="linking" @click="link">
          Link ticket
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
