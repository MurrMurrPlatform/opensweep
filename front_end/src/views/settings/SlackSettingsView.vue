<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { useSlackStore } from '@/stores/slackStore'
import { useRepositoryStore } from '@/stores/repositoryStore'
import { useCurrentUserStore } from '@/stores/currentUserStore'
import { useToast } from '@/composables/useToast'
import type { SlackRuleDTO } from '@/types/api'
import { BellRing, Lock, Plus, Send, Slack as SlackIcon, Trash2, Unplug } from 'lucide-vue-next'

const slack = useSlackStore()
const repos = useRepositoryStore()
const currentUser = useCurrentUserStore()
const toast = useToast()
const route = useRoute()
const router = useRouter()

/** Org admins manage the Slack connection + notification rules. */
const canManage = computed(() => currentUser.isAdmin)

/** Select sentinel — reka-ui SelectItem can't carry the backend's '' value. */
const ALL_REPOS = '__all__'

const loading = ref(true)
const connecting = ref(false)
const disconnectOpen = ref(false)
const disconnecting = ref(false)
/** UID of the rule whose PATCH/POST/DELETE is in flight. */
const togglingRule = ref<string | null>(null)
const testingRule = ref<string | null>(null)
const deletingRule = ref<string | null>(null)

const addOpen = ref(false)
const adding = ref(false)
const form = ref({ event_type: '', channel_id: '', repository: ALL_REPOS, enabled: true })

onMounted(async () => {
  handleOAuthReturn()
  loading.value = true
  try {
    await slack.fetchStatus()
    if (slack.status.connected) await loadConnectedData()
  } catch (e: any) {
    toast.error('Load failed', e.detail || e.message)
  } finally {
    loading.value = false
  }
})

/** The backend OAuth callback 302s here with ?slack=connected|denied|conflict|error. */
function handleOAuthReturn() {
  const flag = route.query.slack
  if (!flag) return
  if (flag === 'connected') {
    toast.success('Slack connected')
  } else if (flag === 'denied') {
    toast.info('Slack connection cancelled', 'The authorization request was denied.')
  } else if (flag === 'conflict') {
    toast.error(
      'Workspace already connected',
      'That Slack workspace is already linked to another organization.',
    )
  } else if (flag === 'error') {
    toast.error('Slack connection failed', 'The OAuth flow did not complete. Try again.')
  }
  router.replace({ query: { ...route.query, slack: undefined } })
}

async function loadConnectedData() {
  await Promise.all([
    slack.fetchRules(),
    // 502 when Slack itself is unhappy — the rules list still renders.
    slack.fetchChannels().catch((e: any) => {
      toast.error('Channel list failed', e.detail || e.message)
    }),
    repos.loaded ? Promise.resolve() : repos.fetchAll().catch(() => {}),
  ])
}

async function connect() {
  connecting.value = true
  try {
    // Full-page redirect to Slack; the callback bounces back to this view.
    await slack.connect()
  } catch (e: any) {
    connecting.value = false
    toast.error('Connect failed', e.detail || e.message)
  }
}

async function confirmDisconnect() {
  disconnecting.value = true
  try {
    await slack.disconnect()
    disconnectOpen.value = false
    toast.success('Slack disconnected')
  } catch (e: any) {
    toast.error('Disconnect failed', e.detail || e.message)
  } finally {
    disconnecting.value = false
  }
}

function eventLabel(eventType: string): string {
  return slack.status.event_types.find((e) => e.event_type === eventType)?.label ?? eventType
}

function eventDescription(eventType: string): string {
  return slack.status.event_types.find((e) => e.event_type === eventType)?.description ?? ''
}

function repoLabel(repositoryUid: string): string {
  if (!repositoryUid) return 'All repositories'
  return repos.find(repositoryUid)?.slug ?? 'Unknown repository'
}

function isPrivateChannel(channelId: string): boolean {
  return slack.channels.find((c) => c.id === channelId)?.is_private ?? false
}

function openAdd() {
  form.value = { event_type: '', channel_id: '', repository: ALL_REPOS, enabled: true }
  addOpen.value = true
}

async function submitRule() {
  const channel = slack.channels.find((c) => c.id === form.value.channel_id)
  if (!channel) return
  adding.value = true
  try {
    await slack.createRule({
      event_type: form.value.event_type,
      channel_id: channel.id,
      channel_name: channel.name,
      repository_uid: form.value.repository === ALL_REPOS ? '' : form.value.repository,
      enabled: form.value.enabled,
    })
    toast.success('Rule added', `${eventLabel(form.value.event_type)} → #${channel.name}`)
    addOpen.value = false
  } catch (e: any) {
    // 409 = duplicate rule or not connected — backend detail says which.
    toast.error('Add rule failed', e.detail || e.message)
  } finally {
    adding.value = false
  }
}

async function toggleRule(rule: SlackRuleDTO, enabled: boolean) {
  togglingRule.value = rule.uid
  try {
    await slack.updateRule(rule.uid, { enabled })
  } catch (e: any) {
    toast.error('Update failed', e.detail || e.message)
  } finally {
    togglingRule.value = null
  }
}

async function sendTest(rule: SlackRuleDTO) {
  testingRule.value = rule.uid
  try {
    await slack.testRule(rule.uid)
    toast.success('Test sent', `#${rule.channel_name}`)
  } catch (e: any) {
    // 502 detail names the Slack error (e.g. channel_not_found when the bot
    // hasn't been invited to a private channel).
    toast.error('Test failed', e.detail || e.message)
  } finally {
    testingRule.value = null
  }
}

async function removeRule(rule: SlackRuleDTO) {
  deletingRule.value = rule.uid
  try {
    await slack.deleteRule(rule.uid)
    toast.success('Rule deleted')
  } catch (e: any) {
    toast.error('Delete failed', e.detail || e.message)
  } finally {
    deletingRule.value = null
  }
}
</script>

<template>
  <div class="space-y-6 max-w-3xl">
    <PageHeader
      title="Slack"
      subtitle="Connect a Slack workspace, route notifications to channels and talk to OpenSweep from Slack."
    />

    <!-- Connection -->
    <Card>
      <CardHeader>
        <div class="flex items-center justify-between gap-2">
          <CardTitle class="text-base flex items-center gap-2">
            <SlackIcon class="h-4 w-4" /> Workspace connection
          </CardTitle>
          <Badge v-if="slack.status.connected" variant="success" class="px-1.5 text-[10px]">connected</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <Skeleton v-if="loading" class="h-16" />

        <!-- Platform operator hasn't configured a Slack app — nobody can connect. -->
        <p v-else-if="!slack.status.configured" class="text-sm text-muted-foreground">
          This deployment has no Slack app configured. A platform operator needs to set
          <code class="text-xs">SLACK_CLIENT_ID</code>, <code class="text-xs">SLACK_CLIENT_SECRET</code> and
          <code class="text-xs">SLACK_SIGNING_SECRET</code> before workspaces can be connected.
        </p>

        <!-- Connected: workspace summary + disconnect. -->
        <div v-else-if="slack.status.connected" class="space-y-3">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div class="min-w-0">
              <div class="text-sm font-medium">{{ slack.status.team_name || slack.status.team_id }}</div>
              <p class="text-xs text-muted-foreground">
                Notifications post as the OpenSweep bot. Invite it to private channels before routing rules there.
              </p>
            </div>
            <Button
              v-if="canManage"
              variant="destructive"
              size="sm"
              class="shrink-0"
              @click="disconnectOpen = true"
            >
              <Unplug /> Disconnect
            </Button>
          </div>
          <p v-if="slack.status.scopes.length" class="text-xs text-muted-foreground">
            Scopes: {{ slack.status.scopes.join(', ') }}
          </p>
        </div>

        <!-- Configured but not connected: install prompt (admins only). -->
        <div v-else class="space-y-3">
          <p class="text-sm text-muted-foreground">
            Connect a Slack workspace to get notifications about findings, runs and pull
            requests in your channels — and to ask OpenSweep questions right from Slack.
          </p>
          <Button v-if="canManage" :loading="connecting" @click="connect">
            <SlackIcon /> Connect Slack workspace
          </Button>
          <p v-else class="text-xs text-muted-foreground">
            An organization admin can connect a Slack workspace.
          </p>
        </div>
      </CardContent>
    </Card>

    <!-- Notification rules -->
    <Card v-if="slack.status.connected">
      <CardHeader>
        <div class="flex items-center justify-between gap-2">
          <CardTitle class="text-base">Notification rules</CardTitle>
          <Button v-if="canManage" size="sm" @click="openAdd">
            <Plus /> Add rule
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div v-if="loading || slack.loadingRules" class="space-y-2">
          <Skeleton v-for="i in 2" :key="i" class="h-14" />
        </div>
        <EmptyState
          v-else-if="!slack.rules.length"
          :icon="BellRing"
          title="No notification rules"
          description="Route an event type to a Slack channel — new findings, run failures, opened PRs and more."
          class="border-0 py-8"
        />
        <div v-else class="stagger-children space-y-2">
          <div
            v-for="rule in slack.rules"
            :key="rule.uid"
            class="flex flex-col gap-3 rounded-md border px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
          >
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="text-sm font-medium">{{ eventLabel(rule.event_type) }}</span>
                <Badge variant="outline" class="px-1.5 text-[10px]">
                  <Lock v-if="isPrivateChannel(rule.channel_id)" class="h-3 w-3" />
                  #{{ rule.channel_name }}
                </Badge>
                <Badge variant="outline" class="px-1.5 text-[10px] text-muted-foreground">
                  {{ repoLabel(rule.repository_uid) }}
                </Badge>
              </div>
              <p v-if="eventDescription(rule.event_type)" class="mt-0.5 text-xs text-muted-foreground">
                {{ eventDescription(rule.event_type) }}
              </p>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <Switch
                :model-value="rule.enabled"
                :disabled="!canManage || togglingRule === rule.uid"
                :aria-label="`Toggle ${eventLabel(rule.event_type)} rule`"
                @update:model-value="toggleRule(rule, $event)"
              />
              <template v-if="canManage">
                <Button
                  size="sm"
                  variant="outline"
                  :loading="testingRule === rule.uid"
                  @click="sendTest(rule)"
                >
                  <Send /> Send test
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  class="text-destructive"
                  :loading="deletingRule === rule.uid"
                  @click="removeRule(rule)"
                >
                  <Trash2 />
                </Button>
              </template>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- How it works -->
    <Card>
      <CardHeader>
        <CardTitle class="text-base">Talking to OpenSweep in Slack</CardTitle>
      </CardHeader>
      <CardContent class="text-sm text-muted-foreground space-y-2">
        <p>
          Once connected, @mention <span class="font-medium text-foreground">@OpenSweep</span> in any
          channel it's in — or DM it — to ask questions about your repositories.
        </p>
        <p>
          The <code class="text-xs">/opensweep</code> slash command works everywhere:
          <code class="text-xs">/opensweep help</code>, <code class="text-xs">/opensweep repos</code>,
          <code class="text-xs">/opensweep runs</code> and <code class="text-xs">/opensweep ask &lt;question&gt;</code>.
          Add <code class="text-xs">repo:&lt;slug&gt;</code> to target a specific workspace.
        </p>
      </CardContent>
    </Card>

    <!-- Disconnect confirm -->
    <Dialog v-model:open="disconnectOpen">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Disconnect Slack</DialogTitle>
          <DialogDescription>
            Notifications stop and the bot leaves your workspace's reach. Notification rules are
            kept and resume if you reconnect the same workspace.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" @click="disconnectOpen = false">Cancel</Button>
          <Button variant="destructive" :loading="disconnecting" @click="confirmDisconnect">
            <Unplug /> Disconnect
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Add rule -->
    <Dialog v-model:open="addOpen">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add notification rule</DialogTitle>
          <DialogDescription>
            Route one event type to one Slack channel, optionally scoped to a repository.
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-3">
          <div class="space-y-1.5">
            <Label for="rule-event">Event</Label>
            <Select v-model="form.event_type">
              <SelectTrigger id="rule-event" class="w-full">
                <SelectValue placeholder="Select an event" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="e in slack.status.event_types" :key="e.event_type" :value="e.event_type">
                  {{ e.label }}
                </SelectItem>
              </SelectContent>
            </Select>
            <p v-if="form.event_type" class="text-xs text-muted-foreground">
              {{ eventDescription(form.event_type) }}
            </p>
          </div>
          <div class="space-y-1.5">
            <Label for="rule-channel">Channel</Label>
            <Select v-model="form.channel_id">
              <SelectTrigger id="rule-channel" class="w-full">
                <SelectValue :placeholder="slack.loadingChannels ? 'Loading channels…' : 'Select a channel'" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="c in slack.channels" :key="c.id" :value="c.id">
                  <span class="inline-flex items-center gap-1">
                    <Lock v-if="c.is_private" class="h-3 w-3 text-muted-foreground" />
                    #{{ c.name }}
                  </span>
                </SelectItem>
              </SelectContent>
            </Select>
            <p v-if="form.channel_id && isPrivateChannel(form.channel_id)" class="text-xs text-muted-foreground">
              Private channel — invite the OpenSweep bot to it or test messages will fail.
            </p>
          </div>
          <div class="space-y-1.5">
            <Label for="rule-repo">Repository</Label>
            <Select v-model="form.repository">
              <SelectTrigger id="rule-repo" class="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem :value="ALL_REPOS">All repositories</SelectItem>
                <SelectItem v-for="r in repos.list" :key="r.uid" :value="r.uid">
                  {{ r.slug }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="flex items-center justify-between gap-3">
            <Label for="rule-enabled">Enabled</Label>
            <Switch id="rule-enabled" v-model="form.enabled" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" @click="addOpen = false">Cancel</Button>
          <Button
            :loading="adding"
            :disabled="!form.event_type || !form.channel_id"
            @click="submitRule"
          >
            <Plus /> Add rule
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
