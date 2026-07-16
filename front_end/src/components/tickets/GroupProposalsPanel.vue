<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Check, Layers, X } from 'lucide-vue-next'
import { useTicketStore } from '@/stores/ticketStore'
import { useToast } from '@/composables/useToast'
import { ApiError } from '@/services/api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { MarkdownView } from '@/components/ui/markdown'
import { priorityVariant } from '@/components/tickets/ticketMeta'
import type { TicketDTO, TicketGroupProposalDTO } from '@/types/api'

interface Props {
  repositoryUid: string
  /** Board tickets — used to resolve member uids to titles. */
  tickets: TicketDTO[]
}
const props = defineProps<Props>()
/** `applied` fires after an approval so the board can reload. */
const emit = defineEmits<{ applied: [] }>()

const store = useTicketStore()
const toast = useToast()

const proposals = ref<TicketGroupProposalDTO[]>([])
const acting = ref<string | null>(null)

async function reload() {
  if (!props.repositoryUid) {
    proposals.value = []
    return
  }
  try {
    proposals.value = await store.listGroupProposals({
      repository_uid: props.repositoryUid,
      status: 'proposed',
    })
  } catch {
    // Non-blocking side panel — the board stays usable without it.
    proposals.value = []
  }
}

watch(() => props.repositoryUid, () => void reload(), { immediate: true })
defineExpose({ reload })

function memberTitle(uid: string): string {
  return props.tickets.find((t) => t.uid === uid)?.title || uid.slice(0, 8)
}

async function approve(p: TicketGroupProposalDTO) {
  if (acting.value) return
  acting.value = p.uid
  try {
    const approved = await store.approveGroupProposal(p.uid)
    proposals.value = proposals.value.filter((x) => x.uid !== p.uid)
    toast.success('Group approved', `Parent ticket created for “${approved.title}”`)
    emit('applied')
  } catch (e) {
    const msg = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)
    toast.error('Approve failed', msg)
  } finally {
    acting.value = null
  }
}

async function reject(p: TicketGroupProposalDTO) {
  if (acting.value) return
  acting.value = p.uid
  try {
    await store.rejectGroupProposal(p.uid)
    proposals.value = proposals.value.filter((x) => x.uid !== p.uid)
    toast.info('Group proposal rejected')
  } catch (e) {
    const msg = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)
    toast.error('Reject failed', msg)
  } finally {
    acting.value = null
  }
}
</script>

<template>
  <Card v-if="proposals.length">
    <CardContent class="space-y-2 p-6">
      <div class="flex items-center gap-2 text-sm font-semibold">
        <Layers class="size-4 text-muted-foreground" /> Proposed ticket groups
        <span class="font-normal text-muted-foreground">· {{ proposals.length }}</span>
      </div>
      <p class="text-xs text-muted-foreground">
        An agent suggests these tickets ship together as one batch. Approving creates a parent
        ticket (in Backlog) with the members as subtickets; nothing changes until you approve.
      </p>
      <div class="divide-y">
        <div v-for="p in proposals" :key="p.uid" class="space-y-1.5 py-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex flex-wrap items-center gap-1.5 text-sm font-medium">
              {{ p.title }}
              <Badge :variant="priorityVariant(p.suggested_priority)" class="px-1.5 text-[10px]">{{ p.suggested_priority }}</Badge>
              <Badge v-for="label in p.suggested_labels" :key="label" variant="secondary" class="px-1.5 text-[10px]">{{ label }}</Badge>
            </div>
            <div class="flex items-center gap-1.5">
              <Button
                variant="outline"
                size="sm"
                :disabled="acting !== null"
                :loading="acting === p.uid"
                @click="approve(p)"
              >
                <Check /> Approve
              </Button>
              <Button variant="ghost" size="sm" :disabled="acting !== null" @click="reject(p)">
                <X /> Reject
              </Button>
            </div>
          </div>
          <MarkdownView v-if="p.rationale" :model-value="p.rationale" preview-only class="text-xs text-muted-foreground" />
          <ul class="space-y-0.5 text-xs">
            <li v-for="uid in p.member_ticket_uids" :key="uid">
              <RouterLink
                :to="{ name: 'ticket-detail', params: { uid } }"
                class="inline-flex items-center gap-1.5 text-muted-foreground hover:text-primary"
              >
                <Layers class="size-3 text-muted-foreground" /> {{ memberTitle(uid) }}
              </RouterLink>
            </li>
          </ul>
        </div>
      </div>
    </CardContent>
  </Card>
</template>
