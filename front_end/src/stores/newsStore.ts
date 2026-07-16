import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiDelete, apiGet, apiPatch, apiPost } from '@/services/api'
import type {
  FindingDTO,
  NewsCategory,
  NewsItemDTO,
  NewsStatus,
  RunDTO,
  UpdateNewsItemRequest,
} from '@/types/api'

export const useNewsStore = defineStore('news', () => {
  const list = ref<NewsItemDTO[]>([])

  async function fetchAll(opts: {
    repository_uid?: string
    category?: NewsCategory
    status?: NewsStatus
  } = {}): Promise<NewsItemDTO[]> {
    const qs = new URLSearchParams()
    Object.entries(opts).forEach(([k, v]) => {
      if (v) qs.set(k, String(v))
    })
    const url = qs.toString() ? `/news?${qs.toString()}` : '/news'
    const data = await apiGet<NewsItemDTO[]>(url)
    list.value = data
    return data
  }

  async function get(uid: string): Promise<NewsItemDTO> {
    return apiGet<NewsItemDTO>(`/news/${uid}`)
  }

  /** Human correction of the digest fields (title/category/summary/relevance/tags). */
  async function update(uid: string, req: UpdateNewsItemRequest): Promise<NewsItemDTO> {
    const item = await apiPatch<NewsItemDTO>(`/news/${uid}`, req)
    list.value = list.value.map((x) => (x.uid === uid ? item : x))
    return item
  }

  async function remove(uid: string): Promise<void> {
    await apiDelete(`/news/${uid}`)
    list.value = list.value.filter((x) => x.uid !== uid)
  }

  async function dismiss(uid: string): Promise<NewsItemDTO> {
    const item = await apiPost<NewsItemDTO>(`/news/${uid}/dismiss`)
    list.value = list.value.map((x) => (x.uid === uid ? item : x))
    return item
  }

  async function save(uid: string): Promise<NewsItemDTO> {
    const item = await apiPost<NewsItemDTO>(`/news/${uid}/save`)
    list.value = list.value.map((x) => (x.uid === uid ? item : x))
    return item
  }

  /** Human-approved conversion: the news item becomes a feature-idea Finding. */
  async function convertToFinding(uid: string): Promise<FindingDTO> {
    return apiPost<FindingDTO>(`/news/${uid}/convert-to-finding`, {})
  }

  /** Dispatch a news-scan run for the repository. */
  async function scan(repository_uid: string): Promise<RunDTO> {
    return apiPost<RunDTO>('/news/scan', { repository_uid })
  }

  /** Dispatch a run that files a best-practices doc proposal as a pending DocEdit. */
  async function docProposal(repository_uid: string): Promise<RunDTO> {
    return apiPost<RunDTO>('/news/doc-proposal', { repository_uid })
  }

  return {
    list,
    fetchAll,
    get,
    update,
    remove,
    dismiss,
    save,
    convertToFinding,
    scan,
    docProposal,
  }
})
