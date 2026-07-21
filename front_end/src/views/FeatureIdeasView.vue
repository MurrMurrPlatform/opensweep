<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Lightbulb, Plus } from 'lucide-vue-next'
import { useFindingStore } from '@/stores/findingStore'
import { formatRelativeTime } from '@/lib/utils'
import { useCurrentRepo } from '@/composables/useCurrentRepo'
import { PageHeader } from '@/components/ui/page-header'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import FindingEditDialog from '@/components/findings/FindingEditDialog.vue'
import type { FindingDTO } from '@/types/api'

const findings = useFindingStore()
const { uid: repoUid } = useCurrentRepo()

const all = ref<FindingDTO[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const createOpen = ref(false)
const tagFilter = ref('')

/** Distinct tags across the loaded ideas — data-driven filter chips. */
const allTags = computed(() => {
  const tags = new Set<string>()
  for (const f of all.value) for (const t of f.tags || []) tags.add(t)
  return Array.from(tags).sort()
})

const items = computed(() => {
  if (!tagFilter.value) return all.value
  return all.value.filter((f) => (f.tags || []).includes(tagFilter.value))
})

/** 2-line teaser: why it matters, else the description — rendered as plain text. */
function excerpt(f: FindingDTO): string {
  return (f.why_it_matters || f.description || '').trim()
}

// Drops stale responses when the workspace switches mid-flight
// (pattern: composables/useActiveRuns.ts).
let reloadGeneration = 0

async function reload() {
  if (!repoUid.value) return
  const gen = ++reloadGeneration
  loading.value = true
  error.value = null
  try {
    const data = await findings.fetchAll({
      status: 'open',
      kind: 'feature-idea',
      repository_uid: repoUid.value,
    })
    if (gen !== reloadGeneration) return
    all.value = data
  } catch (e: unknown) {
    if (gen !== reloadGeneration) return
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (gen === reloadGeneration) loading.value = false
  }
}

onMounted(reload)
watch(repoUid, () => {
  tagFilter.value = ''
  void reload()
})

/** A manually-filed idea lands open — surface it at the top immediately. */
function onFiled(finding: FindingDTO) {
  if (finding.status === 'open' && finding.kind === 'feature-idea' && !all.value.some((f) => f.uid === finding.uid)) {
    all.value = [finding, ...all.value]
  }
}
</script>

<template>
  <div class="space-y-4">
    <PageHeader
      title="Feature ideas"
      subtitle="Product ideas worth building — filed by hand or promoted from the news feed."
    >
      <Button size="sm" :disabled="!repoUid" @click="createOpen = true">
        <Plus /> File idea
      </Button>
    </PageHeader>

    <!-- Tag pill filter -->
    <div v-if="allTags.length" class="flex flex-wrap items-center gap-2">
      <button
        v-for="t in allTags"
        :key="t"
        type="button"
        :class="[
          'rounded-full border px-2.5 py-1 text-xs transition-colors',
          tagFilter === t
            ? 'border-primary bg-primary/10 text-primary'
            : 'border-border text-muted-foreground hover:bg-accent',
        ]"
        @click="tagFilter = tagFilter === t ? '' : t"
      >
        {{ t }}
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <Card v-for="i in 6" :key="i">
        <CardContent class="space-y-1.5 p-4">
          <Skeleton class="h-4 w-2/3" />
          <Skeleton class="h-3 w-1/2" />
          <Skeleton class="h-3 w-1/3" />
        </CardContent>
      </Card>
    </div>

    <!-- Error -->
    <ErrorState v-else-if="error" title="Couldn't load feature ideas" :message="error">
      <Button variant="outline" size="sm" @click="reload">Retry</Button>
    </ErrorState>

    <!-- Empty -->
    <EmptyState
      v-else-if="items.length === 0"
      :icon="Lightbulb"
      title="No feature ideas yet"
      description="File an idea by hand, or run the feature-ideas agent from the News page to promote external signals into ideas."
    />

    <!-- Cards -->
    <div v-else class="stagger-children grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <Card v-for="f in items" :key="f.uid" class="card-interactive hover:bg-accent">
        <CardContent class="p-4">
          <RouterLink
            :to="{ name: 'finding-detail', params: { uid: f.uid } }"
            class="block"
          >
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-medium">{{ f.title }}</span>
              <Badge variant="outline" class="px-1.5 text-[10px]">size: {{ f.size }}</Badge>
              <span
                v-for="t in f.tags || []"
                :key="t"
                class="rounded-full border border-border px-1.5 py-0 text-[10px] text-muted-foreground"
              >
                {{ t }}
              </span>
            </div>
            <p v-if="excerpt(f)" class="mt-1 text-sm text-muted-foreground line-clamp-2">{{ excerpt(f) }}</p>
            <div class="mt-1 text-xs text-muted-foreground">
              {{ f.executor }}
              <template v-if="f.created_at"> · filed {{ formatRelativeTime(f.created_at) }}</template>
            </div>
          </RouterLink>
        </CardContent>
      </Card>
    </div>

    <!-- File an idea by hand -->
    <FindingEditDialog
      v-model:open="createOpen"
      :create-repository-uid="repoUid || ''"
      default-kind="feature-idea"
      @saved="onFiled"
    />
  </div>
</template>
