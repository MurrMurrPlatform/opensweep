import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useRepositoryStore } from '@/stores/repositoryStore'
import type { RepositoryDTO } from '@/types/api'

/**
 * Resolves the workspace selected via the /r/:repoSlug/... route segment.
 *
 * Cold deep-link safe: if the repository isn't in the store yet, we fetch it
 * via GET /repositories/by-slug/{slug}. Re-resolves when :repoSlug changes.
 */
export function useCurrentRepo() {
  const route = useRoute()
  const repos = useRepositoryStore()
  const repo = ref<RepositoryDTO | null>(null)
  const error = ref<unknown>(null)
  const loading = ref(false)

  const slug = computed(() => {
    const raw = route.params.repoSlug
    return Array.isArray(raw) ? raw[0] || null : raw || null
  })

  // Drops stale responses: a slow fetch for a previous slug must never
  // clobber the repo resolved for the current one.
  let generation = 0

  async function resolve(currentSlug: string | null) {
    const gen = ++generation
    error.value = null
    if (!currentSlug) {
      repo.value = null
      return
    }
    const cached = repos.findBySlug(currentSlug)
    if (cached) {
      repo.value = cached
      return
    }
    loading.value = true
    try {
      const resolved = await repos.getBySlug(currentSlug)
      if (gen === generation) repo.value = resolved
    } catch (e) {
      if (gen === generation) {
        error.value = e
        repo.value = null
      }
    } finally {
      if (gen === generation) loading.value = false
    }
  }

  watch(slug, (s) => { void resolve(s) }, { immediate: true })

  /** Re-attempt resolution of the current slug (after a fetch error). */
  function retry() {
    void resolve(slug.value)
  }

  const uid = computed(() => repo.value?.uid ?? null)

  return { slug, uid, repo, loading, error, retry }
}
