import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet, apiPatch } from '@/services/api'
import type { LensDTO, UpdateLensRequest } from '@/types/api'

export const useLensStore = defineStore('lenses', () => {
  const list = ref<LensDTO[]>([])
  const loaded = ref(false)

  async function fetchAll(enabledOnly = false): Promise<LensDTO[]> {
    const data = await apiGet<LensDTO[]>(`/lenses${enabledOnly ? '?enabled_only=true' : ''}`)
    if (!enabledOnly) {
      list.value = data
      loaded.value = true
    }
    return data
  }

  async function get(key: string): Promise<LensDTO> {
    return apiGet<LensDTO>(`/lenses/${key}`)
  }

  async function update(key: string, req: UpdateLensRequest): Promise<LensDTO> {
    const lens = await apiPatch<LensDTO>(`/lenses/${key}`, req)
    list.value = list.value.map((l) => (l.key === lens.key ? lens : l))
    return lens
  }

  return { list, loaded, fetchAll, get, update }
})
