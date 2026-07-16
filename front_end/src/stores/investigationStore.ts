import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiDelete, apiGet, apiPatch, apiPost } from '@/services/api'
import type {
  CreateInvestigationRequest,
  InvestigationDTO,
  InvestigationJobTypeDTO,
  RunDTO,
  RunTrigger,
  UpdateInvestigationRequest,
} from '@/types/api'

export const useInvestigationStore = defineStore('investigations', () => {
  const list = ref<InvestigationDTO[]>([])
  const jobTypes = ref<InvestigationJobTypeDTO[]>([])
  const runsByInvestigation = ref<Record<string, RunDTO[]>>({})

  async function fetchAll(repository_uid?: string): Promise<InvestigationDTO[]> {
    const qs = repository_uid ? `?repository_uid=${repository_uid}` : ''
    const data = await apiGet<InvestigationDTO[]>(`/investigations${qs}`)
    list.value = data
    return data
  }

  async function fetchJobTypes(): Promise<InvestigationJobTypeDTO[]> {
    const data = await apiGet<InvestigationJobTypeDTO[]>(`/investigations/job-types`)
    jobTypes.value = data
    return data
  }

  async function get(uid: string): Promise<InvestigationDTO> {
    return apiGet<InvestigationDTO>(`/investigations/${uid}`)
  }

  async function create(req: CreateInvestigationRequest): Promise<InvestigationDTO> {
    const inv = await apiPost<InvestigationDTO>(`/investigations`, req)
    list.value = [inv, ...list.value]
    return inv
  }

  async function remove(uid: string): Promise<void> {
    await apiDelete(`/investigations/${uid}`)
    list.value = list.value.filter((i) => i.uid !== uid)
  }

  /** Partial update — the scheduling surface (cron, compute dial, target.limit). */
  async function update(uid: string, req: UpdateInvestigationRequest): Promise<InvestigationDTO> {
    const inv = await apiPatch<InvestigationDTO>(`/investigations/${uid}`, req)
    list.value = list.value.map((i) => (i.uid === inv.uid ? inv : i))
    return inv
  }

  async function trigger(
    uid: string,
    opts: { run_policy_uid?: string; trigger?: RunTrigger } = {},
  ): Promise<RunDTO> {
    return apiPost<RunDTO>(`/investigations/${uid}/runs`, opts)
  }

  async function fetchRuns(uid: string): Promise<RunDTO[]> {
    const data = await apiGet<RunDTO[]>(`/investigations/${uid}/runs`)
    runsByInvestigation.value = { ...runsByInvestigation.value, [uid]: data }
    return data
  }

  return { list, jobTypes, runsByInvestigation, fetchAll, fetchJobTypes, get, create, remove, update, trigger, fetchRuns }
})
