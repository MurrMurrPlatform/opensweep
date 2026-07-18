<script setup lang="ts">
// Board/list card for a ticket. One contextual primary action stays inline
// (Approve on backlog — Gate 1; Implement on todo/in-progress); every other
// transition plus Delete lives in the kebab menu and the right-click context
// menu so cards stay scannable.
import { computed, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Check,
  GitPullRequest,
  Layers,
  MoreHorizontal,
  Trash2,
} from 'lucide-vue-next'
import { useTicketStore } from '@/stores/ticketStore'
import { useToast } from '@/composables/useToast'
import { ApiError } from '@/services/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { formatRelativeTime } from '@/lib/utils'
import TicketImplementButton from '@/components/tickets/TicketImplementButton.vue'
import TicketOriginBadge from '@/components/tickets/TicketOriginBadge.vue'
import { TRANSITIONS, priorityVariant, type TicketTransition } from '@/components/tickets/ticketMeta'
import type { TicketDTO } from '@/types/api'

interface Props {
  ticket: TicketDTO
  subticketCount?: number
}
const props = withDefaults(defineProps<Props>(), { subticketCount: 0 })
const emit = defineEmits<{ updated: [ticket: TicketDTO]; deleted: [uid: string] }>()

const store = useTicketStore()
const toast = useToast()
const router = useRouter()

const busy = ref<string | null>(null)
const approveOpen = ref(false)
const deleteOpen = ref(false)

const transitions = computed<TicketTransition[]>(() => TRANSITIONS[props.ticket.status] ?? [])
/** Non-gate moves — the gate (Approve) gets the inline primary button. */
const menuTransitions = computed(() => transitions.value.filter((t) => t.kind !== 'gate'))
const canApprove = computed(() => props.ticket.status === 'backlog')
const canDelete = computed(() => props.ticket.status === 'backlog')
const hasMenu = computed(() => menuTransitions.value.length > 0 || canApprove.value || canDelete.value)

function openTicket() {
  void router.push({ name: 'ticket-detail', params: { uid: props.ticket.uid } })
}

async function transition(t: TicketTransition) {
  if (busy.value) return
  busy.value = t.to
  try {
    const updated = await store.setStatus(props.ticket.uid, t.to)
    approveOpen.value = false
    emit('updated', updated)
    toast.success(t.kind === 'gate' ? 'Ticket approved' : `Moved to ${t.to}`, updated.title)
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e)
    toast.error(e instanceof ApiError && e.status === 409 ? 'Illegal transition' : 'Action failed', msg)
  } finally {
    busy.value = null
  }
}

async function confirmRemove() {
  deleteOpen.value = false
  busy.value = 'delete'
  try {
    await store.deleteTicket(props.ticket.uid)
    emit('deleted', props.ticket.uid)
    toast.success('Ticket deleted', props.ticket.title)
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e)
    toast.error('Delete failed', msg)
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <ContextMenu>
    <ContextMenuTrigger as-child>
      <Card class="group/card space-y-2 p-3 transition-colors hover:border-primary/40">
        <div class="flex items-start justify-between gap-1">
          <RouterLink
            :to="{ name: 'ticket-detail', params: { uid: ticket.uid } }"
            class="block min-w-0 text-sm font-medium transition-colors hover:text-primary"
          >
            {{ ticket.title || '(untitled)' }}
          </RouterLink>
          <DropdownMenu v-if="hasMenu">
            <DropdownMenuTrigger as-child>
              <Button
                variant="ghost"
                size="icon-sm"
                class="-mr-1 -mt-1 size-6 shrink-0 text-muted-foreground sm:opacity-0 sm:transition-opacity sm:focus-visible:opacity-100 sm:group-hover/card:opacity-100 sm:data-[state=open]:opacity-100"
                :title="`Actions for “${ticket.title || 'untitled'}”`"
              >
                <MoreHorizontal class="!size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" class="w-48">
              <DropdownMenuItem @select="openTicket">
                <ArrowUpRight /> Open ticket
              </DropdownMenuItem>
              <DropdownMenuSeparator v-if="canApprove || menuTransitions.length" />
              <DropdownMenuItem v-if="canApprove" :disabled="!!busy" @select="approveOpen = true">
                <Check /> Approve — Gate 1
              </DropdownMenuItem>
              <DropdownMenuItem
                v-for="t in menuTransitions"
                :key="t.to"
                :disabled="!!busy"
                @select="transition(t)"
              >
                <ArrowRight v-if="t.kind === 'forward'" />
                <ArrowLeft v-else />
                {{ t.label }}
              </DropdownMenuItem>
              <template v-if="canDelete">
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  class="text-destructive focus:text-destructive"
                  :disabled="!!busy"
                  @select="deleteOpen = true"
                >
                  <Trash2 /> Delete…
                </DropdownMenuItem>
              </template>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div class="flex flex-wrap items-center gap-1.5">
          <Badge :variant="priorityVariant(ticket.priority)" class="px-1.5 text-[10px]">{{ ticket.priority }}</Badge>
          <Badge v-if="ticket.size" variant="outline" class="px-1.5 text-[10px]">{{ ticket.size }}</Badge>
          <TicketOriginBadge :origin="ticket.origin" />
          <Badge v-if="ticket.linked_pr_uids.length" variant="outline" class="px-1.5 text-[10px]">
            <GitPullRequest class="size-3" /> {{ ticket.linked_pr_uids.length }}
          </Badge>
          <Badge v-if="subticketCount > 0" variant="outline" class="px-1.5 text-[10px]">
            <Layers class="size-3" /> {{ subticketCount }} subticket{{ subticketCount === 1 ? '' : 's' }}
          </Badge>
          <span
            v-if="ticket.created_at"
            class="ml-auto text-[10px] text-muted-foreground"
            :title="`Created ${new Date(ticket.created_at).toLocaleString()}`"
          >{{ formatRelativeTime(ticket.created_at) }}</span>
        </div>

        <div v-if="ticket.labels.length" class="flex flex-wrap gap-1">
          <Badge v-for="label in ticket.labels" :key="label" variant="secondary" class="px-1.5 text-[10px]">{{ label }}</Badge>
        </div>

        <!-- One contextual primary action; the rest lives in the menus. -->
        <div
          v-if="canApprove || ticket.status === 'todo' || ticket.status === 'in-progress'"
          class="flex flex-wrap items-center gap-1.5 pt-1"
        >
          <Button v-if="canApprove" size="sm" :disabled="!!busy" @click="approveOpen = true">
            <Check /> Approve
          </Button>
          <TicketImplementButton v-else compact :ticket="ticket" @updated="emit('updated', $event)" />
        </div>
      </Card>
    </ContextMenuTrigger>

    <ContextMenuContent class="w-48">
      <ContextMenuItem @select="openTicket">
        <ArrowUpRight /> Open ticket
      </ContextMenuItem>
      <ContextMenuSeparator v-if="canApprove || menuTransitions.length" />
      <ContextMenuItem v-if="canApprove" :disabled="!!busy" @select="approveOpen = true">
        <Check /> Approve — Gate 1
      </ContextMenuItem>
      <ContextMenuItem
        v-for="t in menuTransitions"
        :key="t.to"
        :disabled="!!busy"
        @select="transition(t)"
      >
        <ArrowRight v-if="t.kind === 'forward'" />
        <ArrowLeft v-else />
        {{ t.label }}
      </ContextMenuItem>
      <template v-if="canDelete">
        <ContextMenuSeparator />
        <ContextMenuItem
          class="text-destructive focus:text-destructive"
          :disabled="!!busy"
          @select="deleteOpen = true"
        >
          <Trash2 /> Delete…
        </ContextMenuItem>
      </template>
    </ContextMenuContent>
  </ContextMenu>

  <!-- Gate 1 confirm -->
  <Dialog v-model:open="approveOpen">
    <DialogContent class="sm:max-w-lg">
      <DialogHeader>
        <DialogTitle>Approve ticket</DialogTitle>
        <DialogDescription>
          Gate 1: approving moves this ticket from Backlog to Todo. Nothing implements without it.
        </DialogDescription>
      </DialogHeader>
      <p class="text-sm text-muted-foreground">{{ ticket.title }}</p>
      <DialogFooter>
        <Button variant="ghost" size="sm" @click="approveOpen = false">Cancel</Button>
        <Button
          size="sm"
          :loading="busy === 'todo'"
          @click="transition({ to: 'todo', label: 'Approve', kind: 'gate' })"
        >
          <Check /> Approve — move to Todo
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- Delete confirm -->
  <AlertDialog v-model:open="deleteOpen">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>Delete ticket</AlertDialogTitle>
        <AlertDialogDescription>
          Delete “{{ ticket.title }}”? Only backlog tickets can be deleted.
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel>Cancel</AlertDialogCancel>
        <AlertDialogAction
          class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          @click="confirmRemove"
        >
          Delete
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
