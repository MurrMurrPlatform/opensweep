<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Layers } from 'lucide-vue-next'
import { useCampaignStore } from '@/stores/campaignStore'
import { useLensStore } from '@/stores/lensStore'
import { useToast } from '@/composables/useToast'
import { ApiError } from '@/services/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { AgentEffort, CampaignDTO, CampaignTemplate, LensDTO } from '@/types/api'

const props = defineProps<{
  open: boolean
  repositoryUid: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  created: [campaign: CampaignDTO]
}>()

const campaigns = useCampaignStore()
const lensStore = useLensStore()
const toast = useToast()

const template = ref<CampaignTemplate>('rotation')
const effort = ref<AgentEffort | 'default'>('default')
const k = ref(3)
const title = ref('')
const creating = ref(false)
const loadingLenses = ref(false)

/** Local lenses only — global lenses ride along with their sweep agents. */
const localLenses = ref<LensDTO[]>([])
const selectedKeys = ref<Set<string>>(new Set())
/** Focused template picks exactly one lens. */
const focusedKey = ref('')

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    template.value = 'rotation'
    effort.value = 'default'
    k.value = 3
    title.value = ''
    loadingLenses.value = true
    try {
      const all = await lensStore.fetchAll()
      localLenses.value = all.filter((l) => l.scope === 'local')
      // All enabled lenses on by default — matches the backend's "empty =
      // every enabled lens" planning behavior, made explicit.
      selectedKeys.value = new Set(
        localLenses.value.filter((l) => l.enabled).map((l) => l.key),
      )
      focusedKey.value = localLenses.value.find((l) => l.enabled)?.key ?? ''
    } catch (e) {
      toast.error('Couldn’t load lenses', e instanceof Error ? e.message : String(e))
    } finally {
      loadingLenses.value = false
    }
  },
)

function toggleLens(key: string) {
  const next = new Set(selectedKeys.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  selectedKeys.value = next
}

const lensKeys = computed(() =>
  template.value === 'focused'
    ? focusedKey.value
      ? [focusedKey.value]
      : []
    : localLenses.value.filter((l) => selectedKeys.value.has(l.key)).map((l) => l.key),
)

const canCreate = computed(() => {
  if (creating.value || !props.repositoryUid) return false
  if (template.value === 'focused') return !!focusedKey.value
  return lensKeys.value.length > 0
})

async function create() {
  if (!canCreate.value) return
  creating.value = true
  try {
    const campaign = await campaigns.create(props.repositoryUid, {
      template: template.value,
      lens_keys: lensKeys.value,
      effort: effort.value === 'default' ? '' : effort.value,
      k: template.value === 'rotation' ? k.value : undefined,
      title: title.value.trim() || undefined,
    })
    emit('created', campaign)
    emit('update:open', false)
  } catch (e) {
    const msg = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)
    toast.error('Couldn’t create campaign', msg)
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="sm:max-w-2xl">
      <DialogHeader>
        <DialogTitle>New campaign</DialogTitle>
        <DialogDescription>
          Plan a bounded audit sweep of this repository. Nothing runs until you launch it.
        </DialogDescription>
      </DialogHeader>

      <div class="space-y-3">
        <div class="grid gap-3 md:grid-cols-2">
          <div class="space-y-1.5">
            <Label>Template</Label>
            <Select :model-value="template" @update:model-value="template = $event as CampaignTemplate">
              <SelectTrigger class="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="rotation">Rotation — k least-recently-covered areas</SelectItem>
                <SelectItem value="full">Full — all areas + global sweeps</SelectItem>
                <SelectItem value="focused">Focused — one lens everywhere</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-1.5">
            <Label>Effort</Label>
            <Select :model-value="effort" @update:model-value="effort = $event as AgentEffort | 'default'">
              <SelectTrigger class="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="default">Default — areas normal, sweeps deep</SelectItem>
                <SelectItem value="short">Short</SelectItem>
                <SelectItem value="normal">Normal</SelectItem>
                <SelectItem value="deep">Deep</SelectItem>
                <SelectItem value="unlimited">Unlimited</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div v-if="template === 'rotation'" class="space-y-1.5">
          <Label for="campaign-k">Areas this pass (k)</Label>
          <Input id="campaign-k" v-model.number="k" type="number" min="1" class="max-w-32" />
        </div>

        <div class="space-y-1.5">
          <Label>{{ template === 'focused' ? 'Lens' : 'Lenses' }}</Label>
          <div class="max-h-56 overflow-y-auto rounded-md border">
            <div v-if="loadingLenses" class="p-3 text-sm text-muted-foreground">Loading…</div>
            <div v-else-if="!localLenses.length" class="p-3 text-sm text-muted-foreground">
              No local lenses available.
            </div>
            <template v-else-if="template === 'focused'">
              <button
                v-for="l in localLenses"
                :key="l.key"
                type="button"
                class="flex w-full items-start gap-2.5 px-3 py-2 text-left text-sm hover:bg-accent"
                :class="{ 'bg-accent': focusedKey === l.key }"
                @click="focusedKey = l.key"
              >
                <input
                  type="radio"
                  class="mt-1 h-4 w-4 cursor-pointer accent-primary"
                  :checked="focusedKey === l.key"
                  tabindex="-1"
                />
                <span class="min-w-0">
                  <span class="flex flex-wrap items-center gap-1.5 font-medium">
                    {{ l.title || l.key }}
                    <Badge v-if="!l.enabled" variant="outline" class="px-1.5 text-[10px]">disabled</Badge>
                  </span>
                  <span class="block font-mono text-xs text-muted-foreground">{{ l.key }}</span>
                </span>
              </button>
            </template>
            <template v-else>
              <label
                v-for="l in localLenses"
                :key="l.key"
                class="flex cursor-pointer items-start gap-2.5 px-3 py-2 text-sm hover:bg-accent"
              >
                <input
                  type="checkbox"
                  class="mt-1 h-4 w-4 cursor-pointer accent-primary"
                  :checked="selectedKeys.has(l.key)"
                  @change="toggleLens(l.key)"
                />
                <span class="min-w-0">
                  <span class="flex flex-wrap items-center gap-1.5 font-medium">
                    {{ l.title || l.key }}
                    <Badge v-if="!l.enabled" variant="outline" class="px-1.5 text-[10px]">disabled</Badge>
                  </span>
                  <span class="block font-mono text-xs text-muted-foreground">{{ l.key }}</span>
                </span>
              </label>
            </template>
          </div>
        </div>

        <div class="space-y-1.5">
          <Label for="campaign-title">Title (optional)</Label>
          <Input id="campaign-title" v-model="title" placeholder="What is this sweep for?" />
        </div>
      </div>

      <DialogFooter>
        <Button variant="ghost" size="sm" @click="emit('update:open', false)">Cancel</Button>
        <Button size="sm" :disabled="!canCreate" :loading="creating" @click="create">
          <Layers /> Create campaign
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
