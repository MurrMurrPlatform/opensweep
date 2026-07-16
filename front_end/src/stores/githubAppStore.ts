import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiDelete, apiGet, apiPost } from '@/services/api'
import type {
  AvailableReposDTO,
  GitHubAppStatus,
  PatConnectionInfo,
  RegisterRepoRequest,
  RepositoryDTO,
} from '@/types/api'

export const useGithubAppStore = defineStore('github_app', () => {
  const status = ref<GitHubAppStatus>({ connected: false, installations: [] })
  const loaded = ref(false)
  const loading = ref(false)

  async function fetchStatus(): Promise<GitHubAppStatus> {
    loading.value = true
    try {
      status.value = await apiGet<GitHubAppStatus>('/github/app/status')
      loaded.value = true
      return status.value
    } finally {
      loading.value = false
    }
  }

  /** Repos the App can see across all installations, with registered flags.
   *  Not cached — the connect dialog fetches fresh on every open. */
  async function fetchAvailableRepos(): Promise<AvailableReposDTO> {
    return apiGet<AvailableReposDTO>('/github/app/available-repos')
  }

  /** Explicitly register a repo (via an installation or a PAT connection)
   *  as a OpenSweep workspace. 409 = already registered (success-ish). */
  async function registerRepo(req: RegisterRepoRequest): Promise<RepositoryDTO> {
    return apiPost<RepositoryDTO>('/github/app/register-repo', req)
  }

  /** Paste-a-token path: connect a fine-grained PAT to the caller's org. */
  async function addPatConnection(token: string): Promise<PatConnectionInfo> {
    const conn = await apiPost<PatConnectionInfo>('/git/connections', { token })
    await fetchStatus()
    return conn
  }

  async function removePatConnection(uid: string): Promise<void> {
    await apiDelete(`/git/connections/${uid}`)
    await fetchStatus()
  }

  return {
    status,
    loaded,
    loading,
    fetchStatus,
    fetchAvailableRepos,
    registerRepo,
    addPatConnection,
    removePatConnection,
  }
})
