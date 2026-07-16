import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiDelete, apiGet, apiPatch, apiPost } from '@/services/api'

export interface AgentPromptDTO {
  uid: string
  title: string
  description: string
  body: string
  default_job_type: string
  default_scope: 'repository' | 'paths'
  default_effort: 'small' | 'normal' | 'large' | 'quick' | 'deep'
  tags: string[]
  source: 'platform' | 'user' | 'imported'
  source_url: string
  source_commit: string
  enabled: boolean
  created_at?: string | null
  updated_at?: string | null
}

export interface CreateAgentPromptRequest {
  title: string
  description?: string
  body?: string
  default_job_type?: string
  default_scope?: 'repository' | 'paths'
  default_effort?: string
  tags?: string[]
  enabled?: boolean
}

export type UpdateAgentPromptRequest = Partial<CreateAgentPromptRequest>

export interface ImportEccResult {
  imported: number
  skipped_user_edited: number
  source_commit: string
  errors: string[]
}

export const useAgentPromptStore = defineStore('agentPrompts', () => {
  const prompts = ref<AgentPromptDTO[]>([])

  async function fetchAll(filters: { tag?: string; source?: string; enabled_only?: boolean } = {}) {
    const params = new URLSearchParams()
    if (filters.tag) params.set('tag', filters.tag)
    if (filters.source) params.set('source', filters.source)
    if (filters.enabled_only) params.set('enabled_only', 'true')
    const suffix = params.toString() ? `?${params.toString()}` : ''
    const list = await apiGet<AgentPromptDTO[]>(`/agent-prompts${suffix}`)
    prompts.value = list
    return list
  }

  async function fetchByUid(uid: string): Promise<AgentPromptDTO> {
    return apiGet<AgentPromptDTO>(`/agent-prompts/${uid}`)
  }

  async function create(req: CreateAgentPromptRequest): Promise<AgentPromptDTO> {
    return apiPost<AgentPromptDTO>('/agent-prompts', req)
  }

  async function update(uid: string, req: UpdateAgentPromptRequest): Promise<AgentPromptDTO> {
    return apiPatch<AgentPromptDTO>(`/agent-prompts/${uid}`, req)
  }

  async function remove(uid: string): Promise<void> {
    await apiDelete(`/agent-prompts/${uid}`)
  }

  async function importEcc(): Promise<ImportEccResult> {
    return apiPost<ImportEccResult>('/agent-prompts/import-ecc')
  }

  return { prompts, fetchAll, fetchByUid, create, update, remove, importEcc }
})
