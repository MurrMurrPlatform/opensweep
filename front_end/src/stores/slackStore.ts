import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiDelete, apiGet, apiPatch, apiPost } from '@/services/api'
import type {
  SlackChannelDTO,
  SlackRuleCreateRequest,
  SlackRuleDTO,
  SlackRuleUpdateRequest,
  SlackStatusDTO,
} from '@/types/api'

const EMPTY_STATUS: SlackStatusDTO = {
  configured: false,
  connected: false,
  team_id: '',
  team_name: '',
  bot_user_id: '',
  scopes: [],
  installed_by: '',
  event_types: [],
}

export const useSlackStore = defineStore('slack', () => {
  const status = ref<SlackStatusDTO>({ ...EMPTY_STATUS })
  const channels = ref<SlackChannelDTO[]>([])
  const rules = ref<SlackRuleDTO[]>([])
  const loaded = ref(false)
  const loading = ref(false)
  const loadingChannels = ref(false)
  const loadingRules = ref(false)

  async function fetchStatus(): Promise<SlackStatusDTO> {
    loading.value = true
    try {
      status.value = await apiGet<SlackStatusDTO>('/slack/status')
      loaded.value = true
      return status.value
    } finally {
      loading.value = false
    }
  }

  /** Channels the bot can see (404 when not connected, 502 on Slack failure). */
  async function fetchChannels(): Promise<SlackChannelDTO[]> {
    loadingChannels.value = true
    try {
      channels.value = await apiGet<SlackChannelDTO[]>('/slack/channels')
      return channels.value
    } finally {
      loadingChannels.value = false
    }
  }

  async function fetchRules(): Promise<SlackRuleDTO[]> {
    loadingRules.value = true
    try {
      rules.value = await apiGet<SlackRuleDTO[]>('/slack/rules')
      return rules.value
    } finally {
      loadingRules.value = false
    }
  }

  /** Kick off the OAuth install: full-page redirect to Slack. The backend
   *  callback 302s back to /settings/slack?slack=connected|denied|error. */
  async function connect(): Promise<void> {
    const { url } = await apiGet<{ url: string }>('/slack/install')
    window.location.assign(url)
  }

  async function disconnect(): Promise<void> {
    await apiDelete('/slack/connection')
    channels.value = []
    await fetchStatus()
  }

  async function createRule(req: SlackRuleCreateRequest): Promise<SlackRuleDTO> {
    const rule = await apiPost<SlackRuleDTO>('/slack/rules', req)
    rules.value = [...rules.value, rule]
    return rule
  }

  async function updateRule(uid: string, req: SlackRuleUpdateRequest): Promise<SlackRuleDTO> {
    const rule = await apiPatch<SlackRuleDTO>(`/slack/rules/${uid}`, req)
    rules.value = rules.value.map((r) => (r.uid === uid ? rule : r))
    return rule
  }

  async function deleteRule(uid: string): Promise<void> {
    await apiDelete(`/slack/rules/${uid}`)
    rules.value = rules.value.filter((r) => r.uid !== uid)
  }

  /** Send a sample notification through the rule's channel (502 with detail
   *  when Slack rejects it, e.g. bot not invited to a private channel). */
  async function testRule(uid: string): Promise<void> {
    await apiPost(`/slack/rules/${uid}/test`)
  }

  return {
    status,
    channels,
    rules,
    loaded,
    loading,
    loadingChannels,
    loadingRules,
    fetchStatus,
    fetchChannels,
    fetchRules,
    connect,
    disconnect,
    createRule,
    updateRule,
    deleteRule,
    testRule,
  }
})
