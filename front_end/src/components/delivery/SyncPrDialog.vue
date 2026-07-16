<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDeliveryStore } from '@/stores/deliveryStore'
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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { PullRequestDTO, RepositoryDTO } from '@/types/api'

interface Props {
  open: boolean
  repositories: RepositoryDTO[]
}
const props = defineProps<Props>()
const emit = defineEmits<{ 'update:open': [value: boolean]; synced: [pr: PullRequestDTO] }>()

const delivery = useDeliveryStore()
const toast = useToast()

const repositoryUid = ref('')
const numberInput = ref('')
const syncing = ref(false)

const repoOptions = computed(() =>
  props.repositories
    .filter((r) => r.mode === 'github')
    .map((r) => ({ label: r.name, value: r.uid })),
)

const githubNumber = computed(() => {
  const n = parseInt(numberInput.value, 10)
  return Number.isFinite(n) && n > 0 ? n : null
})

const canSync = computed(() => Boolean(repositoryUid.value && githubNumber.value && !syncing.value))

watch(
  () => props.open,
  (open) => {
    if (open && !repositoryUid.value && repoOptions.value.length === 1) {
      repositoryUid.value = repoOptions.value[0].value
    }
  },
)

async function sync() {
  if (!canSync.value || !githubNumber.value) return
  syncing.value = true
  try {
    const pr = await delivery.syncPullRequest(repositoryUid.value, githubNumber.value)
    toast.success('PR synced', `#${pr.github_number} · ${pr.title}`)
    numberInput.value = ''
    emit('synced', pr)
    emit('update:open', false)
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e)
    toast.error('Sync failed', msg)
  } finally {
    syncing.value = false
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="sm:max-w-lg">
      <DialogHeader>
        <DialogTitle>Sync a pull request</DialogTitle>
        <DialogDescription>
          Backfill a PR from GitHub into the convergence ledger — same path the webhook takes.
        </DialogDescription>
      </DialogHeader>
      <div class="space-y-3">
        <div class="space-y-1">
          <Label>Repository</Label>
          <Select v-model="repositoryUid">
            <SelectTrigger class="w-full">
              <SelectValue placeholder="Select a repository…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="o in repoOptions" :key="o.value" :value="o.value">{{ o.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-1">
          <Label>PR number</Label>
          <Input v-model="numberInput" type="number" placeholder="e.g. 72" @keydown.enter="sync" />
        </div>
      </div>
      <DialogFooter>
        <Button variant="ghost" size="sm" @click="emit('update:open', false)">Cancel</Button>
        <Button size="sm" :disabled="!canSync" :loading="syncing" @click="sync">
          Sync PR
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
