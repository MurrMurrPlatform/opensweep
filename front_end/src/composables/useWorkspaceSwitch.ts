import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUiStore } from '@/stores/uiStore'

/**
 * Workspace switching shared by the topbar switcher and the command palette:
 * stay on the same view when it is repo-scoped, otherwise land on the
 * workspace dashboard.
 */
export function useWorkspaceSwitch() {
  const route = useRoute()
  const router = useRouter()
  const ui = useUiStore()

  const currentSlug = computed(() => ui.currentRepoSlug || '')

  function selectWorkspace(slug: string) {
    if (!slug || slug === currentSlug.value) return
    const params = { ...route.params, repoSlug: slug }
    const isScoped = Boolean(route.meta.repoScoped)
    if (isScoped && route.name) {
      // Same view, just swap the workspace.
      router.push({ name: route.name as string, params, query: route.query, hash: route.hash })
    } else {
      // From a global route, land on the workspace dashboard.
      router.push({ name: 'workspace-home', params: { repoSlug: slug } })
    }
  }

  return { currentSlug, selectWorkspace }
}
