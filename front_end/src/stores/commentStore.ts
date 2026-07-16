import { defineStore } from 'pinia'
import { apiDelete, apiGet, apiPost } from '@/services/api'
import type {
  CommentDTO,
  CommentSubjectType,
  CreateCommentRequest,
  MentionSearchResult,
  PendingOpenSweepRunDTO,
} from '@/types/api'

export const useCommentStore = defineStore('comments', () => {
  /** Ascending-by-created_at comment list for one subject. Side-effect free —
   *  each CommentThread owns its own local list. */
  async function fetchFor(subjectType: CommentSubjectType, subjectUid: string): Promise<CommentDTO[]> {
    const qs = new URLSearchParams({ subject_type: subjectType, subject_uid: subjectUid })
    return apiGet<CommentDTO[]>(`/comments?${qs.toString()}`)
  }

  async function create(req: CreateCommentRequest): Promise<CommentDTO> {
    return apiPost<CommentDTO>('/comments', req)
  }

  async function remove(uid: string): Promise<void> {
    await apiDelete(`/comments/${uid}`)
  }

  /** In-flight @opensweep reply runs for a thread — restores the thinking
   *  bubble after a page reload. */
  async function fetchPendingOpenSweepRuns(
    subjectType: CommentSubjectType,
    subjectUid: string,
  ): Promise<PendingOpenSweepRunDTO[]> {
    const qs = new URLSearchParams({ subject_type: subjectType, subject_uid: subjectUid })
    return apiGet<PendingOpenSweepRunDTO[]>(`/comments/pending-opensweep-runs?${qs.toString()}`)
  }

  /** Org-scoped data-item search backing the @-mention dropdown. */
  async function searchMentions(opts: {
    q: string
    types?: string[]
    repository_uid?: string
  }): Promise<MentionSearchResult[]> {
    const qs = new URLSearchParams({ q: opts.q })
    if (opts.types?.length) qs.set('types', opts.types.join(','))
    if (opts.repository_uid) qs.set('repository_uid', opts.repository_uid)
    return apiGet<MentionSearchResult[]>(`/mentions/search?${qs.toString()}`)
  }

  return { fetchFor, create, remove, fetchPendingOpenSweepRuns, searchMentions }
})
