<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { FolderGit2 } from 'lucide-vue-next'
import { useMetricsStore } from '@/stores/metricsStore'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { AnimatedNumber } from '@/components/ui/animated-number'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Button } from '@/components/ui/button'

const metrics = useMetricsStore()

onMounted(metrics.fetchOverview)

const stats = computed(() => {
  const o = metrics.overview
  if (!o) return []
  return [
    {
      key: 'repositories',
      label: 'Repositories',
      value: o.repositories_github,
      detail: 'GitHub',
    },
    {
      key: 'docs',
      label: 'Doc pages',
      value: o.total_docs,
      detail: '',
    },
    {
      key: 'open_findings',
      label: 'Open findings',
      value: o.open_findings,
      detail: `${o.high_severity_findings} high/critical`,
    },
    {
      key: 'proposals',
      label: 'Proposals',
      value: o.proposals,
      detail: `${o.runs_last_24h} runs / 24h`,
    },
  ]
})
</script>

<template>
  <div class="space-y-4">
    <PageHeader
      title="Overview"
      subtitle="Cost-aware repo intelligence — Investigation, Finding, Docs."
    />

    <!-- Loading -->
    <template v-if="metrics.loading && !metrics.overview">
      <section class="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Skeleton v-for="i in 4" :key="i" class="h-24" />
      </section>
      <Skeleton class="h-64" />
      <section class="grid gap-4 sm:grid-cols-2">
        <Skeleton class="h-40" />
        <Skeleton class="h-40" />
      </section>
    </template>

    <!-- Error -->
    <ErrorState
      v-else-if="metrics.error && !metrics.overview"
      title="Couldn't load overview"
      :message="metrics.error.message"
    >
      <Button variant="outline" size="sm" @click="metrics.fetchOverview">Retry</Button>
    </ErrorState>

    <!-- Loaded -->
    <template v-else-if="metrics.overview">
      <section class="stagger-children grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card v-for="s in stats" :key="s.key">
          <CardContent class="p-4">
            <div class="text-xs uppercase tracking-wide text-muted-foreground">{{ s.label }}</div>
            <div class="mt-1 text-2xl font-semibold tabular-nums"><AnimatedNumber :value="s.value" /></div>
            <div v-if="s.detail" class="mt-1 text-xs text-muted-foreground">{{ s.detail }}</div>
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader class="p-4">
          <CardTitle class="text-base">Per repository</CardTitle>
        </CardHeader>
        <CardContent class="p-0">
          <EmptyState
            v-if="metrics.overview.repositories.length === 0"
            :icon="FolderGit2"
            title="No repositories yet"
            description="Connect a repository to start documenting, investigating, and surfacing findings."
            class="rounded-none border-0"
          >
            <Button as="router-link" :to="{ name: 'repositories' }" size="sm">
              Connect a repository
            </Button>
          </EmptyState>
          <Table v-else>
            <TableHeader>
              <TableRow>
                <TableHead>Repository</TableHead>
                <TableHead>Doc pages</TableHead>
                <TableHead>Issues</TableHead>
                <TableHead>High</TableHead>
                <TableHead>Proposals</TableHead>
                <TableHead>Runs / 24h</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="r in metrics.overview.repositories" :key="r.repository_uid">
                <TableCell class="max-w-[320px]">
                  <RouterLink
                    :to="{ name: 'workspace-home', params: { repoSlug: r.repository_slug } }"
                    class="font-medium hover:underline"
                  >
                    {{ r.repository_name }}
                  </RouterLink>
                  <span class="ml-2 font-mono text-xs text-muted-foreground">{{ r.repository_slug }}</span>
                </TableCell>
                <TableCell class="tabular-nums">{{ r.docs }}</TableCell>
                <TableCell class="tabular-nums">{{ r.open_findings }}</TableCell>
                <TableCell class="tabular-nums">{{ r.high_severity_findings }}</TableCell>
                <TableCell class="tabular-nums">{{ r.proposals }}</TableCell>
                <TableCell class="tabular-nums">{{ r.runs_last_24h }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader class="p-4">
          <CardTitle class="text-base">Finding status</CardTitle>
        </CardHeader>
        <CardContent class="p-4 pt-0">
            <p v-if="metrics.overview.finding_statuses.length === 0" class="text-sm text-muted-foreground">
              No findings yet.
            </p>
            <ul v-else class="space-y-1 text-sm">
              <li
                v-for="s in metrics.overview.finding_statuses"
                :key="s.status"
                class="flex justify-between gap-2"
              >
                <span class="font-mono text-xs uppercase text-muted-foreground">{{ s.status }}</span>
                <span class="tabular-nums">{{ s.count }}</span>
              </li>
          </ul>
        </CardContent>
      </Card>
    </template>
  </div>
</template>
