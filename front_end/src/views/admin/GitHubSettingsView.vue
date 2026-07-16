<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useGithubAppStore } from '@/stores/githubAppStore'
import { useToast } from '@/composables/useToast'
import { Github, ExternalLink, FolderGit2, KeyRound, RefreshCw, Trash2 } from 'lucide-vue-next'

const store = useGithubAppStore()
const toast = useToast()

const loading = ref(true)
const token = ref('')
const addingToken = ref(false)
const removingUid = ref('')

onMounted(refresh)

async function refresh() {
  loading.value = true
  try {
    await store.fetchStatus()
  } catch (e: any) {
    toast.error('Status fetch failed', e.detail || e.message)
  } finally {
    loading.value = false
  }
}

function openInstallations() {
  if (store.status.install_url) window.open(store.status.install_url, '_blank')
}

async function addToken() {
  const value = token.value.trim()
  if (!value) return
  addingToken.value = true
  try {
    const conn = await store.addPatConnection(value)
    token.value = ''
    toast.success('Token connected', conn.account ? `Authenticated as ${conn.account}.` : undefined)
  } catch (e: any) {
    toast.error('Token rejected', e.detail || e.message)
  } finally {
    addingToken.value = false
  }
}

async function removeToken(uid: string) {
  removingUid.value = uid
  try {
    await store.removePatConnection(uid)
    toast.success('Token removed')
  } catch (e: any) {
    toast.error('Remove failed', e.detail || e.message)
  } finally {
    removingUid.value = ''
  }
}
</script>

<template>
  <div class="space-y-4 max-w-2xl">
    <PageHeader
      title="GitHub"
      subtitle="Give OpenSweep access to your repositories — with an access token or the GitHub App."
    >
      <Button variant="ghost" size="sm" :disabled="loading" @click="refresh">
        <RefreshCw /> Refresh
      </Button>
    </PageHeader>

    <!-- Access tokens — the self-serve path, works on any deployment. -->
    <Card>
      <CardHeader>
        <div class="flex items-center justify-between gap-2">
          <CardTitle class="text-base flex items-center gap-2">
            <KeyRound class="h-4 w-4" /> Access tokens
          </CardTitle>
          <Badge v-if="store.status.pat_connections?.length" variant="success">
            {{ store.status.pat_connections!.length }} connected
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <Skeleton v-if="loading" class="h-20" />
        <div v-else class="space-y-3">
          <div
            v-for="conn in store.status.pat_connections || []"
            :key="conn.uid"
            class="flex items-center justify-between rounded-md border px-3 py-2"
          >
            <div class="text-sm font-medium">
              {{ conn.account || 'access token' }}
              <span class="ml-2 text-xs font-normal text-muted-foreground">
                added {{ conn.created_at ? conn.created_at.slice(0, 10) : '' }}
              </span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              :loading="removingUid === conn.uid"
              @click="removeToken(conn.uid)"
            >
              <Trash2 /> Remove
            </Button>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <Input
              v-model="token"
              type="password"
              autocomplete="off"
              placeholder="Fine-grained personal access token (github_pat_…)"
              class="min-w-0 flex-1 basis-64 font-mono"
              @keydown.enter="addToken"
            />
            <Button class="shrink-0" :loading="addingToken" :disabled="!token.trim()" @click="addToken">
              <KeyRound /> Connect token
            </Button>
          </div>
          <p class="text-xs text-muted-foreground">
            Create one on GitHub (Settings → Developer settings → Fine-grained tokens) scoped to the
            repositories OpenSweep should see, with Contents + Pull requests read/write. The token is
            stored encrypted and never shown again. Repos you connect through it are available from the
            <RouterLink :to="{ path: '/repositories', query: { connect: '1' } }" class="text-primary hover:underline">
              Repositories page</RouterLink>.
          </p>
        </div>
      </CardContent>
    </Card>

    <!-- GitHub App — installation tokens + webhooks; provisioned by the operator. -->
    <Card>
      <CardHeader>
        <div class="flex items-center justify-between gap-2">
          <CardTitle class="text-base flex items-center gap-2">
            <Github class="h-4 w-4" /> GitHub App
          </CardTitle>
          <Badge v-if="store.status.slug || store.status.app_id" variant="success">Configured</Badge>
          <Badge v-else variant="outline">Not configured</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <Skeleton v-if="loading" class="h-24" />

        <!-- Configured -->
        <div v-else-if="store.status.slug || store.status.app_id" class="space-y-4">
          <div class="flex items-center justify-between gap-4">
            <div>
              <a
                v-if="store.status.html_url"
                :href="store.status.html_url"
                target="_blank"
                class="font-medium text-primary hover:underline inline-flex items-center gap-1"
              >
                {{ store.status.slug || `app #${store.status.app_id}` }}
                <ExternalLink class="h-3.5 w-3.5" />
              </a>
              <div v-else class="font-medium">{{ store.status.slug || `app #${store.status.app_id}` }}</div>
              <div class="text-xs text-muted-foreground mt-1">
                App ID {{ store.status.app_id }} · provisioned by the platform operator
              </div>
            </div>
            <RouterLink :to="{ path: '/repositories', query: { connect: '1' } }">
              <Button variant="outline" size="sm">
                <FolderGit2 /> Browse available repositories
              </Button>
            </RouterLink>
          </div>

          <div>
            <div class="text-xs uppercase tracking-wider text-muted-foreground font-medium mb-2">Installations</div>
            <div v-if="store.status.installations_error" class="text-xs text-warn">
              Could not reach GitHub for live installation data: {{ store.status.installations_error }}
            </div>
            <div v-else-if="store.status.installations.length" class="space-y-2">
              <div
                v-for="inst in store.status.installations"
                :key="inst.id"
                class="flex items-center justify-between rounded-md border px-3 py-2"
              >
                <div class="text-sm font-medium">{{ inst.account || `installation #${inst.id}` }}</div>
                <div class="text-xs text-muted-foreground">
                  {{ inst.repos_count != null ? `${inst.repos_count} repositories` : 'repository count unavailable' }}
                </div>
              </div>
            </div>
            <div v-else class="text-xs text-muted-foreground">
              No installations yet — install the App on your account below, then connect
              repositories from the Repositories page.
            </div>

            <div class="mt-3 flex flex-col gap-3 rounded-md bg-muted px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
              <div class="text-xs text-muted-foreground">
                One app can be installed on your personal account and your organizations.
              </div>
              <Button
                variant="outline"
                size="sm"
                class="shrink-0"
                :disabled="!store.status.install_url"
                @click="openInstallations"
              >
                <ExternalLink /> Install on another account
              </Button>
            </div>
          </div>
        </div>

        <!-- Not configured: the App is deployment config, not a UI flow. -->
        <p v-else class="text-sm text-muted-foreground">
          No GitHub App is configured for this environment — access tokens above work without one.
          The App adds automatic webhooks and short-lived per-repo credentials; the platform operator
          provisions it with <code class="rounded bg-muted px-1 py-0.5 text-xs">scripts/github-app-setup.sh</code>
          (one browser click).
        </p>
      </CardContent>
    </Card>
  </div>
</template>
