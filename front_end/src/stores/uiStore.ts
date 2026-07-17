import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { REPO_SLUG_KEY } from '@/lib/userStorage'

function readPersistedSlug(): string | null {
  try {
    return localStorage.getItem(REPO_SLUG_KEY)
  } catch {
    return null
  }
}

function writePersistedSlug(slug: string | null) {
  try {
    if (slug) localStorage.setItem(REPO_SLUG_KEY, slug)
    else localStorage.removeItem(REPO_SLUG_KEY)
  } catch {
    /* storage unavailable — ignore */
  }
}

export const useUiStore = defineStore('ui', () => {
  const sidebarCollapsed = ref(false)
  const currentRepoSlug = ref<string | null>(readPersistedSlug())

  function toggleSidebar() { sidebarCollapsed.value = !sidebarCollapsed.value }

  function setCurrentRepoSlug(slug: string | null) {
    currentRepoSlug.value = slug || null
  }

  watch(currentRepoSlug, (val) => writePersistedSlug(val))

  return { sidebarCollapsed, currentRepoSlug, toggleSidebar, setCurrentRepoSlug }
})
