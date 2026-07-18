<script setup lang="ts">
// `opensweep connect` — one-copy config so a LOCAL agent (Claude Code, Codex,
// OpenCode) joins the platform over the external MCP mount.
//
// Auth is OAuth 2.1: the backend gateway advertises discovery metadata, the
// client registers itself, your browser opens the consent view, and the
// client holds short-lived tokens it refreshes automatically — no secrets to
// paste. The shared-token header remains a fallback for clients without
// OAuth support (self-host dev).
import { computed, ref } from 'vue'
import { Copy, Plug } from 'lucide-vue-next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useToast } from '@/composables/useToast'

const toast = useToast()

const backendBase = (import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8001').replace(/\/$/, '')
const mcpUrl = computed(() => `${backendBase}/mcp`)

type Client = 'claude' | 'codex' | 'opencode'
const client = ref<Client>('claude')

const snippet = computed(() => {
  if (client.value === 'claude') {
    return `claude mcp add --transport http opensweep ${mcpUrl.value}`
  }
  if (client.value === 'codex') {
    return [
      `codex mcp add opensweep --url ${mcpUrl.value}`,
      'codex mcp login opensweep',
    ].join('\n')
  }
  return [
    '# opencode.json → "mcp" (OAuth via browser on first use)',
    '"opensweep": {',
    '  "type": "remote",',
    `  "url": "${mcpUrl.value}"`,
    '}',
  ].join('\n')
})

async function copy() {
  await navigator.clipboard.writeText(snippet.value)
  toast.success(
    'Config copied',
    'On first use your browser opens OpenSweep to approve the connection.',
  )
}
</script>

<template>
  <Card>
    <CardHeader>
      <CardTitle class="flex items-center gap-2 text-base">
        <Plug class="size-4 text-muted-foreground" /> Connect your local agent
      </CardTitle>
    </CardHeader>
    <CardContent class="space-y-3">
      <p class="text-sm text-muted-foreground">
        Point your local Claude Code, Codex, or OpenCode at OpenSweep’s MCP endpoint. On
        first use, your browser opens an approval screen — sign in with your normal
        account and the agent gets short-lived, auto-refreshing tokens scoped to your
        organization. It can then pull tickets, threads, plans and test notes — say
        “set up ticket #… for testing” — and report results back to the thread. Revoke by
        signing the agent out; tokens also expire on their own.
      </p>
      <div class="flex items-center gap-1.5">
        <Badge
          v-for="c in (['claude', 'codex', 'opencode'] as const)"
          :key="c"
          :variant="client === c ? 'default' : 'outline'"
          class="cursor-pointer select-none"
          @click="client = c"
        >
          {{ c === 'claude' ? 'Claude Code' : c === 'codex' ? 'Codex' : 'OpenCode' }}
        </Badge>
      </div>
      <pre class="overflow-x-auto rounded-md border bg-muted/50 p-3 text-xs">{{ snippet }}</pre>
      <Button size="sm" variant="outline" @click="copy"><Copy /> Copy config</Button>
      <p class="text-[11px] text-muted-foreground">
        Client without OAuth support? Fall back to a header:
        <code>--header "X-OpenSweep-Auth: $OPENSWEEP_AUTH_TOKEN"</code> (self-host only).
      </p>
    </CardContent>
  </Card>
</template>
