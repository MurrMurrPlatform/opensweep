import { ref, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { useRunStore } from '@/stores/runStore'
import { useToast } from '@/composables/useToast'
import { ApiError } from '@/services/api'

/**
 * A subject to open a chat discussion against — the linked_*_uid key names
 * which entity the chat run is bound to. Exactly one linkage key is set.
 */
export interface DiscussSubject {
  repository_uid: string
  /** Chat run title (already prefixed, e.g. "PR #12: …"). */
  title: string
  linked_pr_uid?: string
  linked_ticket_uid?: string
  linked_finding_uid?: string
}

/**
 * Spin up a chat run pre-linked to a subject and jump into it. Dedups the
 * copy-pasted discussInRun handlers across the PR / finding / ticket detail
 * views. Pass a getter returning the subject (or null while it isn't loaded).
 */
export function useDiscussInRun(
  subject: () => DiscussSubject | null,
): { discussing: Ref<boolean>; discuss: () => Promise<void> } {
  const runs = useRunStore()
  const router = useRouter()
  const toast = useToast()
  const discussing = ref(false)

  async function discuss(): Promise<void> {
    const s = subject()
    if (!s || discussing.value) return
    discussing.value = true
    try {
      const run = await runs.createRun({
        repository_uid: s.repository_uid,
        playbook: 'chat',
        title: s.title,
        linked_pr_uid: s.linked_pr_uid,
        linked_ticket_uid: s.linked_ticket_uid,
        linked_finding_uid: s.linked_finding_uid,
      })
      void router.push({ name: 'run-detail', params: { uid: run.uid } })
    } catch (e) {
      const msg = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)
      toast.error('Couldn’t start chat', msg)
    } finally {
      discussing.value = false
    }
  }

  return { discussing, discuss }
}
