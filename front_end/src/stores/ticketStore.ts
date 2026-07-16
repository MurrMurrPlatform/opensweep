import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiDelete, apiGet, apiPatch, apiPost } from '@/services/api'
import type {
  CreateTicketRequest,
  GroupProposalStatus,
  GroupTicketsRequest,
  ImplementRunDispatch,
  ProposeGroupsDispatch,
  PullRequestDTO,
  TicketDTO,
  TicketDetailDTO,
  TicketGroupProposalDTO,
  TicketOrigin,
  TicketStatus,
  UpdateTicketRequest,
} from '@/types/api'

export const useTicketStore = defineStore('tickets', () => {
  const tickets = ref<TicketDTO[]>([])

  function upsert(ticket: TicketDTO) {
    tickets.value = tickets.value.some((x) => x.uid === ticket.uid)
      ? tickets.value.map((x) => (x.uid === ticket.uid ? ticket : x))
      : [...tickets.value, ticket]
  }

  // ── Tickets ─────────────────────────────────────────────────────────────────

  interface TicketFilters {
    repository_uid?: string
    status?: TicketStatus
    origin?: TicketOrigin
    parent_ticket_uid?: string
  }

  /** Side-effect-free list — safe to call in parallel (e.g. link dialogs). */
  async function listTickets(opts: TicketFilters = {}): Promise<TicketDTO[]> {
    const qs = new URLSearchParams()
    Object.entries(opts).forEach(([k, v]) => {
      if (v) qs.set(k, String(v))
    })
    const url = qs.toString() ? `/tickets?${qs.toString()}` : '/tickets'
    return apiGet<TicketDTO[]>(url)
  }

  /** List + replace the store's ticket set (board view). */
  async function fetchTickets(opts: TicketFilters = {}): Promise<TicketDTO[]> {
    const data = await listTickets(opts)
    tickets.value = data
    return data
  }

  async function getTicket(uid: string): Promise<TicketDetailDTO> {
    return apiGet<TicketDetailDTO>(`/tickets/${uid}`)
  }

  async function createTicket(req: CreateTicketRequest): Promise<TicketDTO> {
    const ticket = await apiPost<TicketDTO>('/tickets', req)
    upsert(ticket)
    return ticket
  }

  async function updateTicket(uid: string, req: UpdateTicketRequest): Promise<TicketDTO> {
    const ticket = await apiPatch<TicketDTO>(`/tickets/${uid}`, req)
    upsert(ticket)
    return ticket
  }

  /** Status machine transition — 409 on illegal transitions. backlog→todo is Gate 1. */
  async function setStatus(uid: string, status: TicketStatus): Promise<TicketDTO> {
    const ticket = await apiPost<TicketDTO>(`/tickets/${uid}/status`, { status })
    upsert(ticket)
    return ticket
  }

  async function linkFinding(uid: string, findingUid: string): Promise<TicketDTO> {
    const ticket = await apiPost<TicketDTO>(`/tickets/${uid}/link-finding`, { finding_uid: findingUid })
    upsert(ticket)
    return ticket
  }

  async function linkPullRequest(uid: string, pullRequestUid: string): Promise<TicketDTO> {
    const ticket = await apiPost<TicketDTO>(`/tickets/${uid}/link-pr`, { pull_request_uid: pullRequestUid })
    upsert(ticket)
    return ticket
  }

  /** Write path: dispatch an implement-run — 409 when not todo/in-progress,
   *  an open PR already implements the ticket, or no provider is available. */
  async function implementTicket(uid: string): Promise<ImplementRunDispatch> {
    return apiPost<ImplementRunDispatch>(`/tickets/${uid}/implement`)
  }

  /** Read-only refine-run: sharpen the ticket's title/description/acceptance
   *  criteria and attach an implementation plan via the platform tools. */
  async function refineTicket(uid: string): Promise<ImplementRunDispatch> {
    return apiPost<ImplementRunDispatch>(`/tickets/${uid}/refine`)
  }

  /** Backlog-only delete. */
  async function deleteTicket(uid: string): Promise<void> {
    await apiDelete(`/tickets/${uid}`)
    tickets.value = tickets.value.filter((t) => t.uid !== uid)
  }

  // ── Grouping (batch related tickets under one parent) ───────────────────────

  /** Group ≥2 tickets under a new parent ticket (created in Backlog). */
  async function groupTickets(req: GroupTicketsRequest): Promise<TicketDTO> {
    const parent = await apiPost<TicketDTO>('/tickets/group', req)
    upsert(parent)
    return parent
  }

  /** Dissolve a group: detach every subticket from this parent. */
  async function ungroupTicket(uid: string): Promise<{ ticket_uid: string; detached: number }> {
    return apiPost<{ ticket_uid: string; detached: number }>(`/tickets/${uid}/ungroup`)
  }

  /** Detach a single ticket from its parent group. */
  async function removeFromGroup(uid: string): Promise<TicketDTO> {
    const ticket = await apiPost<TicketDTO>(`/tickets/${uid}/remove-from-group`)
    upsert(ticket)
    return ticket
  }

  /** Dispatch a read-only run that proposes ticket groupings — every
   *  proposal is human-approved before anything changes. 409 when fewer
   *  than 2 ungrouped backlog/todo tickets exist. */
  async function proposeGroups(repositoryUid: string): Promise<ProposeGroupsDispatch> {
    return apiPost<ProposeGroupsDispatch>('/tickets/propose-groups', {
      repository_uid: repositoryUid,
    })
  }

  async function listGroupProposals(opts: {
    repository_uid?: string
    status?: GroupProposalStatus
  } = {}): Promise<TicketGroupProposalDTO[]> {
    const qs = new URLSearchParams()
    Object.entries(opts).forEach(([k, v]) => {
      if (v) qs.set(k, String(v))
    })
    const url = qs.toString() ? `/ticket-group-proposals?${qs.toString()}` : '/ticket-group-proposals'
    return apiGet<TicketGroupProposalDTO[]>(url)
  }

  /** Approve: creates the parent ticket and re-parents the members. */
  async function approveGroupProposal(uid: string): Promise<TicketGroupProposalDTO> {
    return apiPost<TicketGroupProposalDTO>(`/ticket-group-proposals/${uid}/approve`)
  }

  async function rejectGroupProposal(uid: string): Promise<TicketGroupProposalDTO> {
    return apiPost<TicketGroupProposalDTO>(`/ticket-group-proposals/${uid}/reject`)
  }

  // ── PR side of the link (delivery surface) ──────────────────────────────────

  async function linkTicketToPullRequest(pullRequestUid: string, ticketUid: string): Promise<PullRequestDTO> {
    return apiPost<PullRequestDTO>(`/delivery/pull-requests/${pullRequestUid}/link-ticket`, {
      ticket_uid: ticketUid,
    })
  }

  return {
    tickets,
    listTickets,
    fetchTickets,
    getTicket,
    createTicket,
    updateTicket,
    setStatus,
    linkFinding,
    linkPullRequest,
    implementTicket,
    refineTicket,
    deleteTicket,
    groupTickets,
    ungroupTicket,
    removeFromGroup,
    proposeGroups,
    listGroupProposals,
    approveGroupProposal,
    rejectGroupProposal,
    linkTicketToPullRequest,
  }
})
