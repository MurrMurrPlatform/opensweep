import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet, apiPost } from '@/services/api'
import type { PlatformConfigDTO } from '@/types/api'

export const usePlatformConfigStore = defineStore('platform_config', () => {
  const config = ref<PlatformConfigDTO>({ global_kill_switch: false })

  async function fetch(): Promise<PlatformConfigDTO> {
    const data = await apiGet<PlatformConfigDTO>(`/platform-config`)
    config.value = data
    return data
  }

  async function setGlobalKillSwitch(active: boolean): Promise<PlatformConfigDTO> {
    const data = await apiPost<PlatformConfigDTO>(`/platform-config/kill-switch`, { active })
    config.value = data
    return data
  }

  return { config, fetch, setGlobalKillSwitch }
})
