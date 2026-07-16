<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Radar, Telescope } from 'lucide-vue-next'
import { useAnalysisStore, type AnalysisDTO } from '@/stores/analysisStore'
import { useDocStore } from '@/stores/docStore'
import { useCurrentRepo } from '@/composables/useCurrentRepo'
import { useToast } from '@/composables/useToast'
import { ApiError } from '@/services/api'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardContent } from '@/components/ui/card'
import { Badge, type BadgeVariants } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'

const analyses = useAnalysisStore()
const docs = useDocStore()
const toast = useToast()
const { uid: repoUid } = useCurrentRepo()

const items = ref<AnalysisDTO[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const scanning = ref(false)

const sorted = computed(() =>
  [...items.value].sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '')),
)

function statusVariant(s: string): BadgeVariants['variant'] {
  if (s === 'complete') return 'success'
  if (s === 'in_progress') return 'info'
  return 'warn'
}

function daysAgo(iso: string | null): string {
  if (!iso) return '—'
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  return days <= 0 ? 'today' : days === 1 ? '1 day ago' : `${days} days ago`
}

async function load() {
  if (!repoUid.value) return
  loading.value = true
  error.value = null
  try {
    items.value = await analyses.fetchForRepo(repoUid.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function startDeepScan() {
  if (!repoUid.value || scanning.value) return
  scanning.value = true
  try {
    const res = await docs.deepScan(repoUid.value)
    if (res.errors.length) toast.error('Deep scan not dispatched', res.errors.join(' · '))
    else toast.success(res.summary, 'The report will appear here as the scan works through the repo.')
  } catch (e) {
    toast.error('Couldn’t start deep scan', e instanceof ApiError ? e.detail : String(e))
  } finally {
    scanning.value = false
  }
}

onMounted(load)
watch(repoUid, load)
</script>

<template>
  <div class="space-y-4">
    <PageHeader title="Analyses" subtitle="Whole-repo deep-scan reports — verdict, findings, plan, and open questions.">
      <Button size="sm" :loading="scanning" :disabled="!repoUid" @click="startDeepScan">
        <Radar /> Deep scan
      </Button>
    </PageHeader>

    <Card v-if="loading">
      <CardContent class="space-y-2 p-4">
        <Skeleton v-for="i in 5" :key="i" class="h-10" />
      </CardContent>
    </Card>

    <ErrorState v-else-if="error" title="Couldn't load analyses" :message="error">
      <Button variant="outline" size="sm" @click="load">Retry</Button>
    </ErrorState>

    <Card v-else-if="sorted.length">
      <CardContent class="p-0">
        <div class="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Report</TableHead>
                <TableHead>Health</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Findings</TableHead>
                <TableHead>Open questions</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="a in sorted" :key="a.uid">
                <TableCell>
                  <RouterLink
                    :to="{ name: 'analysis-detail', params: { uid: a.uid } }"
                    class="font-medium hover:underline"
                  >
                    {{ a.title || 'Deep scan' }}
                  </RouterLink>
                </TableCell>
                <TableCell>
                  <Badge v-if="a.health_grade" variant="secondary">{{ a.health_grade }}</Badge>
                  <span v-else class="text-muted-foreground">—</span>
                </TableCell>
                <TableCell>
                  <Badge :variant="statusVariant(a.status)">{{ a.status.replace('_', ' ') }}</Badge>
                </TableCell>
                <TableCell class="text-muted-foreground">{{ a.finding_count }}</TableCell>
                <TableCell>
                  <Badge v-if="a.open_question_count" variant="info">{{ a.open_question_count }}</Badge>
                  <span v-else class="text-muted-foreground">—</span>
                </TableCell>
                <TableCell class="whitespace-nowrap text-muted-foreground">{{ daysAgo(a.created_at) }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>

    <Card v-else>
      <CardContent>
        <EmptyState
          :icon="Telescope"
          title="No analyses yet"
          description="Run a deep scan to produce a whole-repo report: verdict, scorecard, findings, a staged plan, and questions to answer."
          class="border-0"
        >
          <Button size="sm" :loading="scanning" :disabled="!repoUid" @click="startDeepScan">
            <Radar /> Deep scan
          </Button>
        </EmptyState>
      </CardContent>
    </Card>
  </div>
</template>
