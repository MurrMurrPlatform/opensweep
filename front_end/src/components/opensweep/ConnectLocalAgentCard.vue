<script setup lang="ts">
// `opensweep connect` — one-copy config so a LOCAL agent (Claude Code, Codex,
// OpenCode) joins the platform over the external MCP mount: pull tickets,
// threads, plans and test notes; report results back as comments. Pairs with
// the "Test locally" button: ask your local agent to set up a ticket's branch
// for testing using the ticket's test note.
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
    return `claude mcp add opensweep --transport http ${mcpUrl.value} --header "X-OpenSweep-Auth: $OPENSWEEP_AUTH_TOKEN"`
  }
  if (client.value === 'codex') {
    return [
      '# ~/.codex/config.toml',
      '[mcp_servers.opensweep]',
      `url = "${mcpUrl.value}"`,
      'http_headers = { "X-OpenSweep-Auth" = "$OPENSWEEP_AUTH_TOKEN" }',
    ].join('\n')
  }
  return [
    '# opencode.json → "mcp"',
    '"opensweep": {',
    '  "type": "remote",',
    `  "url": "${mcpUrl.value}",`,
    '  "headers": { "X-OpenSweep-Auth": "{env:OPENSWEEP_AUTH_TOKEN}" }',
    '}',
  ].join('\n')
})

async function copy() {
  await navigator.clipboard.writeText(snippet.value)
  toast.success('Config copied', 'Set OPENSWEEP_AUTH_TOKEN (from your .env) before starting the agent.')
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
        Point your local Claude Code, Codex, or OpenCode at OpenSweep’s MCP endpoint. Your
        agent can then pull tickets, threads, plans and test notes — say
        “set up ticket #… for testing” and it checks out the branch and follows the test
        note — and report results back to the thread.
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
    </CardContent>
  </Card>
</template>
