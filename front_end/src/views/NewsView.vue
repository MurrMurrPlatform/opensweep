<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import {
  ArrowRight,
  BookOpen,
  Bookmark,
  ExternalLink,
  Lightbulb,
  Loader2,
  MessageSquare,
  Newspaper,
  Radar,
  Sparkles,
  XCircle,
} from 'lucide-vue-next'
import { useNewsStore } from '@/stores/newsStore'
import { useRunStore } from '@/stores/runStore'
import { formatRelativeTime } from '@/lib/utils'
import { useCurrentRepo } from '@/composables/useCurrentRepo'
import { useToast } from '@/composables/useToast'
import { ApiError } from '@/services/api'
import { isLiveRunStatus } from '@/lib/runStatus'
import { PageHeader } from '@/components/ui/page-header'
import { Button } from '@/components/ui/button'
import { Badge, type BadgeVariants } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { MarkdownView } from '@/components/ui/markdown'
import InterestsDialog from '@/components/news/InterestsDialog.vue'
import CommentThread from '@/components/comments/CommentThread.vue'
import type { NewsCategory, NewsItemDTO, NewsStatus } from '@/types/api'

const news = useNewsStore()
const runs = useRunStore()
const { uid: repoUid, slug: repoSlug } = useCurrentRepo()
const toast = useToast()

const all = ref<NewsItemDTO[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const statusTab = ref<NewsStatus>('new')
const categoryFilter = ref<NewsCategory | ''>('')
const interestsOpen = ref(false)
const openDiscussions = ref(new Set<string>())

function toggleDiscussion(uid: string) {
  const next = new Set(openDiscussions.value)
  if (next.has(uid)) next.delete(uid)
  else next.add(uid)
  openDiscussions.value = next
}

// ── Category presentation ────────────────────────────────────────────────────

type BadgeVariant = BadgeVariants['variant']

const CATEGORY_META: Record<NewsCategory, { label: string; badgeVariant: BadgeVariant }> = {
  'trending-repo': { label: 'Trending repo', badgeVariant: 'info' },
  'ai-news': { label: 'AI news', badgeVariant: 'secondary' },
  framework: { label: 'Framework', badgeVariant: 'success' },
  technique: { label: 'Technique', badgeVariant: 'warn' },
  research: { label: 'Research', badgeVariant: 'info' },
  tooling: { label: 'Tooling', badgeVariant: 'secondary' },
  industry: { label: 'Industry', badgeVariant: 'outline' },
}

const CATEGORIES = Object.keys(CATEGORY_META) as NewsCategory[]

// ── Load ─────────────────────────────────────────────────────────────────────

// Drops stale responses when the workspace switches mid-flight
// (pattern: composables/useActiveRuns.ts).
let reloadGeneration = 0

async function reload() {
  if (!repoUid.value) return
  const gen = ++reloadGeneration
  loading.value = true
  error.value = null
  try {
    const data = await news.fetchAll({ repository_uid: repoUid.value })
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
  categoryFilter.value = ''
  stopPolling()
  liveRunUid.value = null
  void reload()
})

// ── Filters ──────────────────────────────────────────────────────────────────

const counts = computed(() => ({
  new: all.value.filter((n) => n.status === 'new').length,
  saved: all.value.filter((n) => n.status === 'saved').length,
  dismissed: all.value.filter((n) => n.status === 'dismissed').length,
  converted: all.value.filter((n) => n.status === 'converted').length,
}))

const items = computed(() => {
  let out = all.value.filter((n) => n.status === statusTab.value)
  if (categoryFilter.value) out = out.filter((n) => n.category === categoryFilter.value)
  return out
})

const emptyCopy = computed(() => {
  switch (statusTab.value) {
    case 'saved':
      return { title: 'Nothing saved', description: 'Save interesting items from the New tab to keep them around.' }
    case 'dismissed':
      return { title: 'Nothing dismissed', description: 'Dismissed items land here — restore them any time.' }
    case 'converted':
      return { title: 'Nothing converted yet', description: 'Convert a news item to file it as a feature-idea finding.' }
    default:
      return { title: 'No news yet', description: 'Run a scan to let the agent pull in external signals relevant to this workspace.' }
  }
})

// ── Row transitions (save / restore / dismiss) ───────────────────────────────

const actingUid = ref('')

function patchLocal(updated: NewsItemDTO) {
  all.value = all.value.map((x) => (x.uid === updated.uid ? updated : x))
}

async function saveItem(item: NewsItemDTO) {
  if (actingUid.value) return
  actingUid.value = item.uid
  try {
    patchLocal(await news.save(item.uid))
  } catch (e) {
    const msg = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)
    toast.error('Save failed', msg)
  } finally {
    actingUid.value = ''
  }
}

async function dismissItem(item: NewsItemDTO) {
  if (actingUid.value) return
  actingUid.value = item.uid
  try {
    patchLocal(await news.dismiss(item.uid))
  } catch (e) {
    const msg = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)
    toast.error('Dismiss failed', msg)
  } finally {
    actingUid.value = ''
  }
}

// ── Convert to finding (human-approved) ──────────────────────────────────────

const convertTarget = ref<NewsItemDTO | null>(null)
const converting = ref(false)

async function confirmConvert() {
  const item = convertTarget.value
  if (!item || converting.value) return
  converting.value = true
  try {
    const finding = await news.convertToFinding(item.uid)
    all.value = all.value.map((x) =>
      x.uid === item.uid ? { ...x, status: 'converted' as NewsStatus, converted_finding_uid: finding.uid } : x,
    )
    convertTarget.value = null
    toast.success('Feature idea filed', finding.title, {
      label: 'View finding',
      to: { name: 'finding-detail', params: { uid: finding.uid } },
    })
  } catch (e) {
    const msg = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)
    toast.error('Convert failed', msg)
  } finally {
    converting.value = false
  }
}

// ── Scan now (dispatch + poll until the run settles) ─────────────────────────

const scanning = ref(false)
const liveRunUid = ref<string | null>(null)
let pollTimer: number | undefined

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

async function pollScan() {
  const uid = liveRunUid.value
  if (!uid) {
    stopPolling()
    return
  }
  try {
    const run = await runs.get(uid)
    if (!isLiveRunStatus(run.status)) {
      stopPolling()
      liveRunUid.value = null
      await reload()
      toast.success('News scan complete', undefined, {
        label: 'View run',
        to: { name: 'run-detail', params: { uid } },
      })
    }
  } catch {
    /* transient poll error — keep trying */
  }
}

async function scanNow() {
  if (!repoUid.value || scanning.value || liveRunUid.value) return
  scanning.value = true
  try {
    const run = await news.scan(repoUid.value)
    liveRunUid.value = run.uid
    toast.success('Scan dispatched', `run ${run.uid.slice(0, 8)}`, {
      label: 'View run',
      to: { name: 'run-detail', params: { uid: run.uid } },
    })
    stopPolling()
    pollTimer = window.setInterval(pollScan, 2500)
  } catch (e) {
    const msg = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)
    toast.error('Scan failed', msg)
  } finally {
    scanning.value = false
  }
}

onBeforeUnmount(stopPolling)

// ── Best-practices doc proposal ──────────────────────────────────────────────

const proposing = ref(false)

async function proposeDoc() {
  if (!repoUid.value || proposing.value) return
  proposing.value = true
  try {
    const run = await news.docProposal(repoUid.value)
    toast.success(
      'Doc proposal dispatched',
      'The agent will file a pending edit in Documentation.',
      { label: 'View run', to: { name: 'run-detail', params: { uid: run.uid } } },
    )
  } catch (e) {
    const msg = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)
    toast.error('Doc proposal failed', msg)
  } finally {
    proposing.value = false
  }
}
</script>

<template>
  <div class="space-y-4">
    <PageHeader
      title="News"
      subtitle="External signals scanned for this workspace — save what matters, convert the best into feature ideas."
    >
      <Button variant="ghost" size="sm" @click="interestsOpen = true">
        <Sparkles /> Interests
      </Button>
      <Button variant="outline" size="sm" :disabled="!repoUid" :loading="proposing" @click="proposeDoc">
        <BookOpen v-if="!proposing" /> Generate best-practices doc
      </Button>
      <Button
        size="sm"
        :disabled="!repoUid || !!liveRunUid"
        :loading="scanning"
        @click="scanNow"
      >
        <Radar v-if="!scanning" />
        {{ liveRunUid ? 'Scan running…' : 'Scan now' }}
      </Button>
    </PageHeader>

    <p class="text-xs text-muted-foreground -mt-2">
      Doc proposals land as pending edits in
      <RouterLink
        v-if="repoSlug"
        :to="{ name: 'documentation', params: { repoSlug } }"
        class="text-primary hover:underline"
      >Documentation</RouterLink>
      <template v-else>Documentation</template>.
    </p>

    <!-- Live scan banner -->
    <div
      v-if="liveRunUid"
      class="flex items-center gap-2 rounded-md border border-border bg-muted px-3 py-2 text-sm"
    >
      <Loader2 class="h-4 w-4 animate-spin text-muted-foreground" />
      <span>News scan in progress —</span>
      <RouterLink
        :to="{ name: 'run-detail', params: { uid: liveRunUid } }"
        class="font-mono text-primary hover:underline"
      >{{ liveRunUid.slice(0, 8) }}</RouterLink>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap items-center gap-3">
      <Tabs :model-value="statusTab" @update:model-value="statusTab = $event as NewsStatus">
        <TabsList class="max-w-full overflow-x-auto">
          <TabsTrigger value="new">
            New <Badge variant="secondary" class="ml-1.5 px-1.5 text-[10px]">{{ counts.new }}</Badge>
          </TabsTrigger>
          <TabsTrigger value="saved">
            Saved <Badge variant="secondary" class="ml-1.5 px-1.5 text-[10px]">{{ counts.saved }}</Badge>
          </TabsTrigger>
          <TabsTrigger value="dismissed">
            Dismissed <Badge variant="secondary" class="ml-1.5 px-1.5 text-[10px]">{{ counts.dismissed }}</Badge>
          </TabsTrigger>
          <TabsTrigger value="converted">
            Converted <Badge variant="secondary" class="ml-1.5 px-1.5 text-[10px]">{{ counts.converted }}</Badge>
          </TabsTrigger>
        </TabsList>
      </Tabs>
      <div class="flex flex-wrap items-center gap-2">
        <button
          v-for="c in CATEGORIES"
          :key="c"
          type="button"
          :class="[
            'rounded-full border px-2.5 py-0.5 text-xs transition-colors',
            categoryFilter === c
              ? 'border-primary bg-primary/10 text-primary'
              : 'border-border text-muted-foreground hover:bg-accent',
          ]"
          @click="categoryFilter = categoryFilter === c ? '' : c"
        >
          {{ CATEGORY_META[c].label }}
        </button>
      </div>
    </div>

    <!-- Loading -->
    <Card v-if="loading">
      <CardContent class="p-0">
        <ul class="divide-y divide-border px-4">
          <li v-for="i in 4" :key="i" class="space-y-1.5 py-4">
            <Skeleton class="h-4 w-2/3" />
            <Skeleton class="h-3 w-1/2" />
            <Skeleton class="h-3 w-full" />
          </li>
        </ul>
      </CardContent>
    </Card>

    <!-- Error -->
    <ErrorState v-else-if="error" title="Couldn't load news" :message="error">
      <Button variant="outline" size="sm" @click="reload">Retry</Button>
    </ErrorState>

    <!-- Empty -->
    <EmptyState
      v-else-if="items.length === 0"
      :icon="Newspaper"
      :title="emptyCopy.title"
      :description="emptyCopy.description"
    />

    <!-- List -->
    <Card v-else>
      <CardContent class="p-0">
        <div class="stagger-children divide-y divide-border">
          <div v-for="item in items" :key="item.uid" class="space-y-2 p-4">
            <!-- Title -->
            <div class="flex flex-wrap items-start justify-between gap-2">
              <a
                v-if="item.url"
                :href="item.url"
                target="_blank"
                rel="noopener noreferrer"
                class="inline-flex min-w-0 items-center gap-1.5 font-medium text-foreground hover:text-primary hover:underline"
              >
                <span class="truncate">{{ item.title }}</span>
                <ExternalLink class="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              </a>
              <span v-else class="font-medium">{{ item.title }}</span>

              <!-- Actions by status -->
              <div class="flex shrink-0 flex-wrap items-center gap-2">
                <template v-if="item.status === 'new'">
                  <Button variant="outline" size="sm" :disabled="!!actingUid" @click="saveItem(item)">
                    <Bookmark /> Save
                  </Button>
                  <Button variant="ghost" size="sm" :disabled="!!actingUid" @click="dismissItem(item)">
                    <XCircle /> Dismiss
                  </Button>
                  <Button size="sm" :disabled="converting" @click="convertTarget = item">
                    <Lightbulb /> Convert to finding
                  </Button>
                </template>
                <template v-else-if="item.status === 'saved'">
                  <Button variant="ghost" size="sm" :disabled="!!actingUid" @click="dismissItem(item)">
                    <XCircle /> Dismiss
                  </Button>
                  <Button size="sm" :disabled="converting" @click="convertTarget = item">
                    <Lightbulb /> Convert to finding
                  </Button>
                </template>
                <template v-else-if="item.status === 'dismissed'">
                  <Button variant="outline" size="sm" :disabled="!!actingUid" @click="saveItem(item)">
                    <Bookmark /> Restore
                  </Button>
                </template>
                <RouterLink
                  v-else-if="item.status === 'converted' && item.converted_finding_uid"
                  :to="{ name: 'finding-detail', params: { uid: item.converted_finding_uid } }"
                  class="inline-flex items-center gap-1 whitespace-nowrap text-xs text-primary hover:underline"
                >
                  View finding <ArrowRight class="h-3 w-3" />
                </RouterLink>
              </div>
            </div>

            <!-- Meta row -->
            <div class="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span class="font-mono">{{ item.source }}</span>
              <Badge :variant="CATEGORY_META[item.category]?.badgeVariant || 'secondary'" class="px-1.5 text-[10px]">
                {{ CATEGORY_META[item.category]?.label || item.category }}
              </Badge>
              <span
                v-for="t in item.tags || []"
                :key="t"
                class="rounded-full border border-border px-1.5 py-0 text-[10px] text-muted-foreground"
              >
                {{ t }}
              </span>
              <span>{{ formatRelativeTime(item.published_at ?? item.created_at) }}</span>
            </div>

            <!-- Summary -->
            <MarkdownView v-if="item.summary" :model-value="item.summary" preview-only />

            <!-- Relevance callout -->
            <div
              v-if="item.relevance && item.relevance.trim()"
              class="rounded-md border-l-2 border-primary bg-primary/5 px-3 py-2"
            >
              <div class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-primary">
                Why this matters here
              </div>
              <MarkdownView :model-value="item.relevance" preview-only />
            </div>

            <!-- Discussion (collapsed by default) -->
            <button
              type="button"
              class="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
              @click="toggleDiscussion(item.uid)"
            >
              <MessageSquare class="size-3.5" />
              {{ openDiscussions.has(item.uid) ? 'Hide discussion' : 'Discussion' }}
            </button>
            <CommentThread
              v-if="openDiscussions.has(item.uid)"
              subject-type="news_item"
              :subject-uid="item.uid"
              :repository-uid="item.repository_uid"
              title="Discussion"
            />
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- Convert confirm -->
    <Dialog :open="!!convertTarget" @update:open="convertTarget = null">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Convert to feature idea</DialogTitle>
          <DialogDescription>
            A human-approved conversion — the news item becomes a feature-idea Finding.
          </DialogDescription>
        </DialogHeader>
        <div v-if="convertTarget" class="space-y-3 text-sm">
          <p class="font-medium">{{ convertTarget.title }}</p>
          <ul class="list-disc space-y-1 pl-5 text-muted-foreground">
            <li>Creates an open <strong>feature-idea</strong> finding on this workspace's Ideas page.</li>
            <li>The finding carries the item's summary and its relevance to this repository.</li>
            <li>The news item moves to the Converted tab and links to the finding.</li>
          </ul>
        </div>
        <DialogFooter>
          <Button variant="ghost" size="sm" @click="convertTarget = null">Cancel</Button>
          <Button size="sm" :loading="converting" @click="confirmConvert">
            <Lightbulb /> Convert
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <InterestsDialog v-model:open="interestsOpen" :repository-uid="repoUid || ''" />
  </div>
</template>
