<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { usePlatformConfigStore } from '@/stores/platformConfigStore'
import { useToast } from '@/composables/useToast'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

const cfg = usePlatformConfigStore()
const toast = useToast()
const loading = ref(true)
const toggling = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    await cfg.fetch()
  } finally {
    loading.value = false
  }
})

async function toggleGlobal() {
  toggling.value = true
  try {
    await cfg.setGlobalKillSwitch(!cfg.config.global_kill_switch)
    toast.success(cfg.config.global_kill_switch ? 'Kill switch engaged' : 'Kill switch released')
  } catch (e: unknown) {
    toast.error('Toggle failed', e instanceof Error ? e.message : String(e))
  } finally {
    toggling.value = false
  }
}
</script>

<template>
  <div class="space-y-4 max-w-3xl">
    <PageHeader
      title="Platform config"
      subtitle="Global kill switch for every InvestigationRun dispatch."
    />

    <Card>
      <CardHeader>
        <CardTitle class="text-base">Global kill switch</CardTitle>
      </CardHeader>
      <CardContent>
        <Skeleton v-if="loading" class="h-20" />
        <div v-else class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div class="text-xs text-muted-foreground">
              When active, every Run dispatch returns 409 — autonomous AND human-triggered.
            </div>
            <div class="text-xs text-muted-foreground mt-1">
              Last changed: {{ cfg.config.updated_at || '—' }}
            </div>
          </div>
          <Button
            :variant="cfg.config.global_kill_switch ? 'destructive' : 'outline'"
            size="sm"
            :loading="toggling"
            class="shrink-0"
            @click="toggleGlobal"
          >
            {{ cfg.config.global_kill_switch ? 'Active — click to release' : 'Engage kill switch' }}
          </Button>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
