import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiDelete, apiGet, apiPatch, apiPost } from '@/services/api'
import type { LLMProvider, LLMProviderKindMeta, LLMProviderStatus } from '@/types/api'

export const useLLMProviderStore = defineStore('llmProviders', () => {
  const list = ref<LLMProvider[]>([])
  const loaded = ref(false)
  const catalog = ref<LLMProviderKindMeta[]>([])
  const status = ref<LLMProviderStatus | null>(null)

  async function fetchAll() {
    list.value = await apiGet<LLMProvider[]>('/llm-providers')
    loaded.value = true
  }

  async function fetchStatus() {
    status.value = await apiGet<LLMProviderStatus>('/llm-providers/status')
  }

  /** Refresh readiness after any mutation — fire-and-forget. */
  function refreshStatus() {
    fetchStatus().catch(() => {})
  }

  async function fetchCatalog() {
    if (catalog.value.length) return
    catalog.value = await apiGet<LLMProviderKindMeta[]>('/llm-providers/catalog')
  }

  function find(uid: string) { return list.value.find(p => p.uid === uid) }

  async function create(req: Partial<LLMProvider>): Promise<LLMProvider> {
    const p = await apiPost<LLMProvider>('/llm-providers', req)
    list.value = [...list.value, p]
    refreshStatus()
    return p
  }

  async function update(uid: string, req: Partial<LLMProvider>): Promise<LLMProvider> {
    const p = await apiPatch<LLMProvider>(`/llm-providers/${uid}`, req)
    list.value = list.value.map(x => (x.uid === uid ? p : x))
    refreshStatus()
    return p
  }

  async function remove(uid: string): Promise<void> {
    await apiDelete(`/llm-providers/${uid}`)
    list.value = list.value.filter(x => x.uid !== uid)
    refreshStatus()
  }

  async function check(uid: string): Promise<LLMProvider> {
    const p = await apiPost<LLMProvider>(`/llm-providers/${uid}/check`)
    list.value = list.value.map(x => (x.uid === uid ? p : x))
    return p
  }

  async function setActive(uid: string): Promise<LLMProvider> {
    const p = await update(uid, { active: true, enabled: true })
    return p
  }

  return { list, loaded, catalog, status, fetchAll, fetchCatalog, fetchStatus, find, create, update, remove, check, setActive }
})
