// Per-user localStorage keys, cleared on sign-out so the next account on
// this browser doesn't inherit the previous user's workspace or session
// state. Device preferences (opensweep:theme:*, opensweep_notification_sounds)
// and the operator shared-token credential (opensweep_auth_token)
// intentionally survive sign-out.

export const REPO_SLUG_KEY = 'opensweep.currentRepoSlug'
export const CHAT_ACTIVE_RUN_KEY = 'opensweep-chat-active-run'
export const BOARD_PREFS_PREFIX = 'opensweep:board:'

export function clearPersistedUserState(): void {
  try {
    localStorage.removeItem(REPO_SLUG_KEY)
    localStorage.removeItem(CHAT_ACTIVE_RUN_KEY)
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith(BOARD_PREFS_PREFIX)) localStorage.removeItem(key)
    }
  } catch {
    /* storage unavailable — nothing persisted to clear */
  }
}
