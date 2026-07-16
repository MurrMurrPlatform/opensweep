import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiDelete, apiGet, apiPatch, apiPost } from '@/services/api'
import type { RunPolicyDTO } from '@/types/api'

export const useRunPolicyStore = defineStore('run_policies', () => {
  const list = ref<RunPolicyDTO[]>([])

  async function fetchAll(): Promise<RunPolicyDTO[]> {
    const data = await apiGet<RunPolicyDTO[]>(`/run-policies`)
    list.value = data
    return data
  }

  async function get(uid: string): Promise<RunPolicyDTO> {
    return apiGet<RunPolicyDTO>(`/run-policies/${uid}`)
  }

  async function create(req: Partial<RunPolicyDTO>): Promise<RunPolicyDTO> {
    const p = await apiPost<RunPolicyDTO>(`/run-policies`, req)
    list.value = [p, ...list.value]
    return p
  }

  async function update(uid: string, req: Partial<RunPolicyDTO>): Promise<RunPolicyDTO> {
    const p = await apiPatch<RunPolicyDTO>(`/run-policies/${uid}`, req)
    list.value = list.value.map((x) => (x.uid === uid ? p : x))
    return p
  }

  async function remove(uid: string): Promise<void> {
    await apiDelete(`/run-policies/${uid}`)
    list.value = list.value.filter((p) => p.uid !== uid)
  }

  return { list, fetchAll, get, create, update, remove }
})
