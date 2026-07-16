// Org agent overlays — per-playbook org tuning of agent task instructions
// (spec: docs/superpowers/specs/2026-07-14-org-agent-overlays-design.md).
// Platform structural framing stays in code; orgs append to (or replace) the
// platform task-instructions layer per playbook.
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiDelete, apiGet, apiPost, apiPut } from '@/services/api'

export type OverlayMode = 'append' | 'replace'

export interface AgentOverlayDTO {
  uid: string
  playbook: string
  mode: OverlayMode
  body: string
  enabled: boolean
  rev: number
  updated_by: string
  created_at?: string | null
  updated_at?: string | null
}

/** Read-only preview of the seeded platform base for a playbook. */
export interface PlatformBaseDTO {
  uid: string
  title: string
  body: string
  enabled: boolean
  source_url: string
}

export interface PlaybookOverlayStatusDTO {
  playbook: string
  /** null: platform base row deleted — the in-code default intent is used. */
  platform: PlatformBaseDTO | null
  /** null: org runs platform defaults for this playbook. */
  overlay: AgentOverlayDTO | null
}

export interface OverlayRevisionDTO {
  uid: string
  playbook: string
  rev: number
  mode: OverlayMode
  body: string
  enabled: boolean
  author_uid: string
  created_at?: string | null
}

export interface UpsertOverlayRequest {
  mode: OverlayMode
  body: string
  enabled: boolean
}

export interface OverlayPreviewResponse {
  playbook: string
  mode: OverlayMode
  prompt: string
}

export const useAgentOverlayStore = defineStore('agentOverlays', () => {
  /** One entry per playbook, in backend order (chat … refine). */
  const entries = ref<PlaybookOverlayStatusDTO[]>([])
  const loaded = ref(false)

  function patchEntry(playbook: string, overlay: AgentOverlayDTO | null) {
    entries.value = entries.value.map((e) =>
      e.playbook === playbook ? { ...e, overlay } : e,
    )
  }

  async function fetchAll(): Promise<PlaybookOverlayStatusDTO[]> {
    entries.value = await apiGet<PlaybookOverlayStatusDTO[]>('/agent-overlays')
    loaded.value = true
    return entries.value
  }

  /** Upsert the org overlay for a playbook; writes a new revision. */
  async function upsert(playbook: string, req: UpsertOverlayRequest): Promise<AgentOverlayDTO> {
    const overlay = await apiPut<AgentOverlayDTO>(`/agent-overlays/${playbook}`, req)
    patchEntry(playbook, overlay)
    return overlay
  }

  /** Restore platform default — removes the overlay; history is kept. */
  async function restoreDefault(playbook: string): Promise<void> {
    await apiDelete(`/agent-overlays/${playbook}`)
    patchEntry(playbook, null)
  }

  async function fetchRevisions(playbook: string): Promise<OverlayRevisionDTO[]> {
    return apiGet<OverlayRevisionDTO[]>(`/agent-overlays/${playbook}/revisions`)
  }

  /** Revert = save a new revision copying an old one (history is append-only). */
  async function revert(playbook: string, rev: number): Promise<AgentOverlayDTO> {
    const overlay = await apiPost<AgentOverlayDTO>(`/agent-overlays/${playbook}/revert`, { rev })
    patchEntry(playbook, overlay)
    return overlay
  }

  /** Compose the full prompt for a draft overlay — never persisted. */
  async function preview(
    playbook: string,
    req: { mode: OverlayMode; body: string },
  ): Promise<OverlayPreviewResponse> {
    return apiPost<OverlayPreviewResponse>(`/agent-overlays/${playbook}/preview`, req)
  }

  return { entries, loaded, fetchAll, upsert, restoreDefault, fetchRevisions, revert, preview }
})
