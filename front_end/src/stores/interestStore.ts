import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiDelete, apiGet, apiPatch, apiPost } from '@/services/api'
import type { InterestDTO } from '@/types/api'

export const useInterestStore = defineStore('interests', () => {
  const list = ref<InterestDTO[]>([])

  async function fetchAll(opts: { repository_uid: string }): Promise<InterestDTO[]> {
    const qs = new URLSearchParams({ repository_uid: opts.repository_uid })
    const data = await apiGet<InterestDTO[]>(`/interests?${qs.toString()}`)
    list.value = data
    return data
  }

  async function create(req: {
    repository_uid: string
    title: string
    details: string
    enabled: boolean
  }): Promise<InterestDTO> {
    const i = await apiPost<InterestDTO>('/interests', req)
    list.value = [i, ...list.value]
    return i
  }

  async function update(
    uid: string,
    req: { title?: string; details?: string; enabled?: boolean },
  ): Promise<InterestDTO> {
    const i = await apiPatch<InterestDTO>(`/interests/${uid}`, req)
    list.value = list.value.map((x) => (x.uid === uid ? i : x))
    return i
  }

  async function remove(uid: string): Promise<void> {
    await apiDelete(`/interests/${uid}`)
    list.value = list.value.filter((x) => x.uid !== uid)
  }

  return { list, fetchAll, create, update, remove }
})
