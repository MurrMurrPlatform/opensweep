import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiDelete, apiGet } from '@/services/api'
import type { MemoryDTO } from '@/types/api'

export const useMemoryStore = defineStore('memories', () => {
  const list = ref<MemoryDTO[]>([])

  async function fetchAll(opts: {
    repository_uid?: string
    anchor_uid?: string
    q?: string
  } = {}): Promise<MemoryDTO[]> {
    const qs = new URLSearchParams()
    Object.entries(opts).forEach(([k, v]) => {
      if (v) qs.set(k, String(v))
    })
    const url = qs.toString() ? `/memories?${qs.toString()}` : '/memories'
    const data = await apiGet<MemoryDTO[]>(url)
    list.value = data
    return data
  }

  /** Human curation is a delete button — memories have no approval lifecycle. */
  async function remove(uid: string): Promise<void> {
    await apiDelete(`/memories/${uid}`)
    list.value = list.value.filter((m) => m.uid !== uid)
  }

  return { list, fetchAll, remove }
})
