import { defineStore } from 'pinia'
import { apiGet, apiPut } from '@/services/api'
import type { AnalyzersConfig, UpdateWorkflowRequest, WorkflowConfig } from '@/types/api'

export const useWorkflowStore = defineStore('workflow', () => {
  async function fetchForRepo(repositoryUid: string): Promise<WorkflowConfig> {
    return apiGet<WorkflowConfig>(`/repositories/${repositoryUid}/workflow`)
  }

  /** 422 when a referenced agent prompt is missing or disabled. */
  async function update(repositoryUid: string, req: UpdateWorkflowRequest): Promise<WorkflowConfig> {
    return apiPut<WorkflowConfig>(`/repositories/${repositoryUid}/workflow`, req)
  }

  // ── Static-analyzer config (sibling per-repo config) ──────────────────────

  async function fetchAnalyzers(repositoryUid: string): Promise<AnalyzersConfig> {
    return apiGet<AnalyzersConfig>(`/repositories/${repositoryUid}/analyzers`)
  }

  async function updateAnalyzers(
    repositoryUid: string,
    req: AnalyzersConfig,
  ): Promise<AnalyzersConfig> {
    return apiPut<AnalyzersConfig>(`/repositories/${repositoryUid}/analyzers`, req)
  }

  return { fetchForRepo, update, fetchAnalyzers, updateAnalyzers }
})
