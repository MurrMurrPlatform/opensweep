import { ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useRunStore } from '@/stores/runStore'
import type { RunDTO } from '@/types/api'

/** A discussion is "open" while a follow-up message would continue it —
 *  awaiting_input included (unlike /runs/active, which only reports in-flight
 *  turns). Ended/failed chats drop off the chip. */
const OPEN_STATUSES = new Set(['queued', 'running', 'awaiting_input', 'paused_quota'])

export interface DiscussionFilters {
  repository_uid?: string
  linked_pr_uid?: string
  linked_ticket_uid?: string
  linked_finding_uid?: string
}

/**
 * Open chat runs linked to a subject — feeds the non-blocking DiscussionChip
 * on ticket/finding/PR detail pages. One fetch per subject change (no
 * polling: a conversation chip doesn't need live status).
 */
export function useDiscussions(filters: MaybeRefOrGetter<DiscussionFilters | null | undefined>) {
  const runs = useRunStore()
  const discussions = ref<RunDTO[]>([])
  let generation = 0 // drops stale responses when the subject changes mid-flight

  async function refresh(): Promise<RunDTO[]> {
    const f = toValue(filters)
    if (!f || Object.values(f).every((v) => !v)) {
      generation += 1
      discussions.value = []
      return []
    }
    const gen = ++generation
    try {
      const data = await runs.query({ ...f, playbook: 'chat', limit: 20 })
      if (gen === generation) {
        discussions.value = data.filter((r) => OPEN_STATUSES.has(r.status))
      }
    } catch {
      /* transient fetch error — keep the last known state */
    }
    return discussions.value
  }

  watch(
    () => toValue(filters),
    () => void refresh(),
    { immediate: true, deep: true },
  )

  return { discussions, refresh }
}
