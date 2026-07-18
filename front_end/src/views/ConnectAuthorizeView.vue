<script setup lang="ts">
// OAuth consent for `opensweep connect` (unified dev flow, cloud auth).
// The backend gateway (/oauth/authorize) validated the client and redirected
// here; this view runs as the LOGGED-IN user (the router's auth guard sends
// anonymous visitors through the Zitadel login first). Approving calls the
// authenticated approve endpoint, which re-validates everything server-side,
// mints the single-use code, and returns the client redirect to follow.
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Plug, ShieldCheck, X } from 'lucide-vue-next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ApiError, apiPost } from '@/services/api'
import { useCurrentUserStore } from '@/stores/currentUserStore'

const route = useRoute()
const currentUser = useCurrentUserStore()

const clientId = computed(() => String(route.query.client_id ?? ''))
const clientName = computed(() => String(route.query.client_name ?? 'An MCP client'))
const redirectUri = computed(() => String(route.query.redirect_uri ?? ''))
const state = computed(() => String(route.query.state ?? ''))
const codeChallenge = computed(() => String(route.query.code_challenge ?? ''))
const scope = computed(() => String(route.query.scope ?? 'mcp:read'))

const valid = computed(() => Boolean(clientId.value && redirectUri.value && codeChallenge.value))
const scopes = computed(() => scope.value.split(' ').filter(Boolean))

const SCOPE_DESCRIPTIONS: Record<string, string> = {
  'mcp:read': 'Read tickets, threads, plans, pull requests, docs and memories in your organization; post comments.',
  'mcp:write': 'Additionally update tickets and file findings on your behalf.',
}

const busy = ref(false)
const error = ref<string | null>(null)

function clientRedirect(params: Record<string, string>) {
  const qs = new URLSearchParams(params).toString()
  const sep = redirectUri.value.includes('?') ? '&' : '?'
  window.location.href = `${redirectUri.value}${sep}${qs}`
}

async function approve() {
  if (busy.value) return
  busy.value = true
  error.value = null
  try {
    const result = await apiPost<{ redirect_to: string }>('/oauth-mcp/approve', {
      client_id: clientId.value,
      redirect_uri: redirectUri.value,
      state: state.value,
      code_challenge: codeChallenge.value,
      scope: scope.value,
    })
    window.location.href = result.redirect_to
  } catch (e) {
    error.value = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)
    busy.value = false
  }
}

function deny() {
  const params: Record<string, string> = { error: 'access_denied' }
  if (state.value) params.state = state.value
  clientRedirect(params)
}
</script>

<template>
  <div class="grid min-h-[70vh] place-items-center p-6">
    <Card class="w-full max-w-md">
      <CardHeader>
        <CardTitle class="flex items-center gap-2 text-base">
          <Plug class="size-4 text-muted-foreground" /> Connect a local agent
        </CardTitle>
      </CardHeader>
      <CardContent class="space-y-4">
        <template v-if="!valid">
          <p class="text-sm text-bad">
            This authorization link is incomplete — start the connection again from your
            MCP client.
          </p>
        </template>
        <template v-else>
          <p class="text-sm">
            <span class="font-semibold">{{ clientName }}</span> wants to access OpenSweep as
            <span class="font-semibold">{{ currentUser.displayName || 'you' }}</span
            >, inside your organization only.
          </p>
          <ul class="space-y-2">
            <li v-for="s in scopes" :key="s" class="flex items-start gap-2 text-sm">
              <ShieldCheck class="mt-0.5 size-4 shrink-0 text-good" />
              <span>
                <Badge variant="outline" class="mr-1 px-1.5 text-[10px]">{{ s }}</Badge>
                {{ SCOPE_DESCRIPTIONS[s] ?? s }}
              </span>
            </li>
          </ul>
          <p class="text-xs text-muted-foreground">
            The client receives short-lived tokens that it refreshes automatically. You can
            revoke access at any time by signing the agent out, and tokens expire on their
            own.
          </p>
          <p v-if="error" class="text-sm text-bad">{{ error }}</p>
          <div class="flex gap-2">
            <Button class="flex-1" :loading="busy" @click="approve">Approve</Button>
            <Button class="flex-1" variant="outline" :disabled="busy" @click="deny">
              <X /> Deny
            </Button>
          </div>
        </template>
      </CardContent>
    </Card>
  </div>
</template>
