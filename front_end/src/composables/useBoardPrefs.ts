import type { Ref } from 'vue'
import { reactive, watch } from 'vue'
import type { TicketStatus } from '@/types/api'
import { BOARD_PREFS_PREFIX } from '@/lib/userStorage'

export interface BoardPrefs {
  hidden: TicketStatus[]
  collapsed: TicketStatus[]
}

const ACTIVE_LANES: TicketStatus[] = ['todo', 'in-progress', 'in-review']

function storageKey(repoUid: string) {
  return `${BOARD_PREFS_PREFIX}${repoUid}`
}

function load(repoUid: string): BoardPrefs {
  try {
    const raw = localStorage.getItem(storageKey(repoUid))
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<BoardPrefs>
      return {
        hidden: Array.isArray(parsed.hidden) ? parsed.hidden : [],
        collapsed: Array.isArray(parsed.collapsed) ? parsed.collapsed : [],
      }
    }
  } catch { /* corrupted or private mode — fall through to defaults */ }
  return { hidden: [], collapsed: [] }
}

/**
 * Per-repository kanban view preferences (hidden + collapsed lanes),
 * persisted in localStorage so the board opens the way you left it.
 */
export function useBoardPrefs(repoUid: Ref<string | null | undefined>) {
  const prefs = reactive<BoardPrefs>({ hidden: [], collapsed: [] })

  watch(repoUid, (uid) => {
    const loaded = uid ? load(uid) : { hidden: [], collapsed: [] }
    prefs.hidden = loaded.hidden
    prefs.collapsed = loaded.collapsed
  }, { immediate: true })

  watch(prefs, () => {
    if (!repoUid.value) return
    try {
      localStorage.setItem(storageKey(repoUid.value), JSON.stringify(prefs))
    } catch { /* private mode — prefs just don't persist */ }
  }, { deep: true })

  const isHidden = (s: TicketStatus) => prefs.hidden.includes(s)
  const isCollapsed = (s: TicketStatus) => prefs.collapsed.includes(s)

  function setHidden(s: TicketStatus, hidden: boolean) {
    prefs.hidden = hidden ? [...new Set([...prefs.hidden, s])] : prefs.hidden.filter(x => x !== s)
  }

  function toggleCollapsed(s: TicketStatus) {
    prefs.collapsed = isCollapsed(s) ? prefs.collapsed.filter(x => x !== s) : [...prefs.collapsed, s]
  }

  /** Preset: only the active work lanes (hide Backlog and Done). */
  function focusActive() {
    prefs.hidden = (['backlog', 'done'] as TicketStatus[])
    prefs.collapsed = prefs.collapsed.filter(s => ACTIVE_LANES.includes(s) === false)
  }

  /** Preset: everything visible and expanded. */
  function showAll() {
    prefs.hidden = []
    prefs.collapsed = []
  }

  return { prefs, isHidden, isCollapsed, setHidden, toggleCollapsed, focusActive, showAll }
}
