import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet, apiPost } from '@/services/api'
import type { AnalysisDTO, RefineAnalysisResponse } from '@/types/api'

// DTOs live in types/api.ts (mirror back_end/domains/analysis/schemas.py).
export type {
  AnalysisDTO,
  AnalysisQuestion,
  AnalysisStatus,
  CoverageEntry,
  QuestionStatus,
  ScorecardEntry,
  StrengthEntry,
  ValidationEntry,
} from '@/types/api'

export const useAnalysisStore = defineStore('analysis', () => {
  const list = ref<AnalysisDTO[]>([])

  async function fetchForRepo(
    repoUid: string,
    opts: { status?: string; includeSuperseded?: boolean } = {},
  ): Promise<AnalysisDTO[]> {
    const qs = new URLSearchParams({ repository_uid: repoUid })
    if (opts.status) qs.set('status', opts.status)
    if (opts.includeSuperseded === false) qs.set('include_superseded', 'false')
    const data = await apiGet<AnalysisDTO[]>(`/analyses?${qs.toString()}`)
    list.value = data
    return data
  }

  async function get(uid: string): Promise<AnalysisDTO> {
    return apiGet<AnalysisDTO>(`/analyses/${uid}`)
  }

  /** Newest non-superseded Analysis for a repo (Health's "current" report). */
  async function latestForRepo(repoUid: string): Promise<AnalysisDTO | null> {
    return apiGet<AnalysisDTO | null>(`/analyses/latest?repository_uid=${encodeURIComponent(repoUid)}`)
  }

  async function answerQuestion(uid: string, qid: string, answer: string): Promise<AnalysisDTO> {
    return apiPost<AnalysisDTO>(`/analyses/${uid}/questions/${qid}/answer`, { answer })
  }

  async function dismissQuestion(uid: string, qid: string): Promise<AnalysisDTO> {
    return apiPost<AnalysisDTO>(`/analyses/${uid}/questions/${qid}/dismiss`)
  }

  /** Dispatch a fresh deep-scan that ingests the answered questions; the new
   *  run's Analysis supersedes this one. 409 if a deep scan is already running. */
  async function refineWithAnswers(uid: string): Promise<RefineAnalysisResponse> {
    return apiPost<RefineAnalysisResponse>(`/analyses/${uid}/refine`)
  }

  return { list, fetchForRepo, get, latestForRepo, answerQuestion, dismissQuestion, refineWithAnswers }
})
