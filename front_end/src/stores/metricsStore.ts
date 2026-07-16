import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet } from '@/services/api'
import type { OverviewMetrics } from '@/types/api'

export const useMetricsStore = defineStore('metrics', () => {
  const overview = ref<OverviewMetrics | null>(null)
  const loading = ref(false)
  const error = ref<Error | null>(null)

  async function fetchOverview() {
    loading.value = true
    error.value = null
    try {
      overview.value = await apiGet<OverviewMetrics>('/overview')
    } catch (e) {
      error.value = e as Error
    } finally {
      loading.value = false
    }
  }

  return { overview, loading, error, fetchOverview }
})
