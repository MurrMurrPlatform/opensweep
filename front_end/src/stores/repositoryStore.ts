import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiDelete, apiGet, apiPatch, apiPost } from '@/services/api'
import { useUiStore } from '@/stores/uiStore'
import type { RepositoryDTO } from '@/types/api'

export const useRepositoryStore = defineStore('repositories', () => {
  const list = ref<RepositoryDTO[]>([])
  const loaded = ref(false)

  async function fetchAll(): Promise<RepositoryDTO[]> {
    list.value = await apiGet<RepositoryDTO[]>('/repositories')
    loaded.value = true
    return list.value
  }

  function find(uid: string): RepositoryDTO | undefined {
    return list.value.find((r) => r.uid === uid)
  }

  function findBySlug(slug: string): RepositoryDTO | undefined {
    return list.value.find((r) => r.slug === slug)
  }

  async function get(uid: string): Promise<RepositoryDTO> {
    const cached = find(uid)
    if (cached) return cached
    const r = await apiGet<RepositoryDTO>(`/repositories/${uid}`)
    if (!list.value.some((x) => x.uid === r.uid)) list.value = [...list.value, r]
    return r
  }

  async function getBySlug(slug: string): Promise<RepositoryDTO> {
    const cached = findBySlug(slug)
    if (cached) return cached
    const r = await apiGet<RepositoryDTO>(`/repositories/by-slug/${slug}`)
    if (!list.value.some((x) => x.uid === r.uid)) list.value = [...list.value, r]
    return r
  }

  async function create(req: Partial<RepositoryDTO>): Promise<RepositoryDTO> {
    const r = await apiPost<RepositoryDTO>('/repositories', req)
    list.value = [...list.value, r]
    return r
  }

  async function update(uid: string, req: Partial<RepositoryDTO>): Promise<RepositoryDTO> {
    const r = await apiPatch<RepositoryDTO>(`/repositories/${uid}`, req)
    list.value = list.value.map((x) => (x.uid === uid ? r : x))
    return r
  }

  async function remove(uid: string): Promise<void> {
    const gone = find(uid)
    await apiDelete(`/repositories/${uid}`)
    list.value = list.value.filter((r) => r.uid !== uid)
    if (gone) {
      const ui = useUiStore()
      if (ui.currentRepoSlug === gone.slug) ui.setCurrentRepoSlug(null)
    }
  }

  return { list, loaded, fetchAll, find, findBySlug, get, getBySlug, create, update, remove }
})
