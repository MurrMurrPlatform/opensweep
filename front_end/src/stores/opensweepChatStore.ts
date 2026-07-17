import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useRunStore } from '@/stores/runStore'
import type { CreateRunRequest, RunDTO } from '@/types/api'
import { CHAT_ACTIVE_RUN_KEY as ACTIVE_KEY } from '@/lib/userStorage'

/**
 * OpenSweep chat-bubble sessions. A session IS a run (playbook=chat,
 * surface=chat) — this store tracks which one the widget shows and the
 * recent-history list; the widget owns the live socket and message list.
 */
export const useOpenSweepChatStore = defineStore('opensweepChat', () => {
  const runs = useRunStore()

  const sessions = ref<RunDTO[]>([])
  const sessionsLoading = ref(false)
  const activeRunUid = ref<string | null>(localStorage.getItem(ACTIVE_KEY))

  function setActive(uid: string | null) {
    activeRunUid.value = uid
    if (uid) localStorage.setItem(ACTIVE_KEY, uid)
    else localStorage.removeItem(ACTIVE_KEY)
  }

  /** The caller's own chat sessions, newest first (server ordering). */
  async function loadSessions(): Promise<RunDTO[]> {
    sessionsLoading.value = true
    try {
      sessions.value = await runs.query({ surface: 'chat', limit: 20 })
      return sessions.value
    } finally {
      sessionsLoading.value = false
    }
  }

  /** Start a fresh session from the first message. The backend resolves the
   *  repository from the context subject when repositoryUid is null. */
  async function startSession(opts: {
    prompt: string
    repositoryUid: string | null
    context?: { subject_type: string; subject_uid: string }
  }): Promise<RunDTO> {
    const req: CreateRunRequest = {
      repository_uid: opts.repositoryUid ?? '',
      playbook: 'chat',
      surface: 'chat',
      prompt: opts.prompt,
      title: opts.prompt.length > 64 ? `${opts.prompt.slice(0, 64)}…` : opts.prompt,
      context: opts.context,
    }
    const run = await runs.createRun(req)
    setActive(run.uid)
    sessions.value = [run, ...sessions.value]
    return run
  }

  return { sessions, sessionsLoading, activeRunUid, setActive, loadSessions, startSession }
})
