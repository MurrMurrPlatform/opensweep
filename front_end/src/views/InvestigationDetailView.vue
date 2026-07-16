<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { CalendarClock } from 'lucide-vue-next'
import { useInvestigationStore } from '@/stores/investigationStore'
import { useToast } from '@/composables/useToast'
import { ApiError } from '@/services/api'
import { PageHeader } from '@/components/ui/page-header'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import CommentThread from '@/components/comments/CommentThread.vue'
import type { ComputeDial, InvestigationDTO, RunDTO } from '@/types/api'

const route = useRoute()
const invs = useInvestigationStore()
const toast = useToast()
const inv = ref<InvestigationDTO | null>(null)
const runs = ref<RunDTO[]>([])
const loading = ref(true)
const triggering = ref(false)

// ── Schedule editor — the automation surface of a saved Investigation ───────
type ScheduleMode = 'manual' | 'on-event' | 'cron'
const scheduleMode = ref<ScheduleMode>('manual')
const cronExpr = ref('')
const dial = ref<ComputeDial>('ask-before-run')
const savingSchedule = ref(false)

const SCHEDULE_OPTIONS = [
  { label: 'Manual — run only when triggered', value: 'manual' },
  { label: 'On push — when a push touches its target', value: 'on-event' },
  { label: 'Cron — on a schedule', value: 'cron' },
]

const DIAL_OPTIONS = [
  { label: 'Disabled — never runs automatically', value: 'disabled' },
  { label: 'Suggest — surface as a candidate only', value: 'suggest' },
  { label: 'Ask before run', value: 'ask-before-run' },
  { label: 'Auto-run on free (local) compute', value: 'auto-run-cheap' },
  { label: 'Auto-run on any provider', value: 'auto-run-any' },
]

const CRON_PRESETS = [
  { label: 'Nightly at 02:00', expr: '0 2 * * *' },
  { label: 'Every 6 hours', expr: '0 */6 * * *' },
  { label: 'Weekly (Mon 06:00)', expr: '0 6 * * 1' },
]

function hydrateSchedule(i: InvestigationDTO) {
  if (i.schedule.startsWith('cron:')) {
    scheduleMode.value = 'cron'
    cronExpr.value = i.schedule.slice('cron:'.length)
  } else if (i.schedule === 'on-event') {
    scheduleMode.value = 'on-event'
    cronExpr.value = ''
  } else {
    scheduleMode.value = 'manual'
    cronExpr.value = ''
  }
  dial.value = i.compute_dial
}

/** target.limit of the seeded audit-stale Investigation — pages per tick. */
const auditLimit = computed(() => {
  const raw = inv.value?.target?.limit
  return typeof raw === 'number' && raw > 0 ? raw : 3
})

const scheduleDirty = computed(() => {
  if (!inv.value) return false
  const next =
    scheduleMode.value === 'cron'
      ? `cron:${cronExpr.value.trim()}`
      : scheduleMode.value === 'on-event'
        ? 'on-event'
        : ''
  return next !== inv.value.schedule || dial.value !== inv.value.compute_dial
})

async function saveSchedule() {
  if (!inv.value || savingSchedule.value) return
  if (scheduleMode.value === 'cron' && !cronExpr.value.trim()) {
    toast.error('Cron expression required', 'Pick a preset or enter a 5-field crontab.')
    return
  }
  savingSchedule.value = true
  try {
    inv.value = await invs.update(inv.value.uid, {
      schedule:
        scheduleMode.value === 'cron'
          ? `cron:${cronExpr.value.trim()}`
          : scheduleMode.value === 'on-event'
            ? 'on-event'
            : '',
      compute_dial: dial.value,
    })
    hydrateSchedule(inv.value)
    toast.success('Schedule saved')
  } catch (e) {
    const msg = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e)
    toast.error('Couldn’t save schedule', msg)
  } finally {
    savingSchedule.value = false
  }
}

onMounted(load)

async function load() {
  loading.value = true
  try {
    inv.value = await invs.get(String(route.params.uid))
    hydrateSchedule(inv.value)
    runs.value = await invs.fetchRuns(inv.value.uid)
  } finally {
    loading.value = false
  }
}

async function trigger() {
  if (!inv.value || triggering.value) return
  triggering.value = true
  try {
    await invs.trigger(inv.value.uid)
    runs.value = await invs.fetchRuns(inv.value.uid)
    toast.success('Run dispatched')
  } catch (e: unknown) {
    toast.error('Trigger failed', e instanceof Error ? e.message : String(e))
  } finally {
    triggering.value = false
  }
}
</script>

<template>
  <div class="space-y-4">
    <template v-if="loading && !inv">
      <Skeleton class="h-12 w-2/3" />
      <Skeleton class="h-24" />
      <Skeleton class="h-32" />
    </template>

    <template v-else-if="inv">
      <PageHeader :title="inv.title || inv.intent.slice(0, 80)">
        <template #breadcrumb>
          <div class="mb-1 font-mono text-xs uppercase text-muted-foreground">{{ inv.job_type }} · {{ inv.effort }}</div>
        </template>
      </PageHeader>

      <Card>
        <CardContent class="p-4">
          <p class="whitespace-pre-line text-sm">{{ inv.intent }}</p>
        </CardContent>
      </Card>

      <Card>
        <CardContent class="flex flex-wrap items-center justify-between gap-3 p-4">
          <div class="text-sm text-muted-foreground">
            Uses the active LLM provider. Runs are tracking-only and cannot apply code changes.
          </div>
          <Button size="sm" :loading="triggering" @click="trigger">
            Run now
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader class="flex-row items-center justify-between gap-3 space-y-0 p-4">
          <CardTitle class="flex items-center gap-2 text-base">
            <CalendarClock class="h-4 w-4 text-muted-foreground" /> Schedule
          </CardTitle>
          <Button
            size="sm"
            :disabled="!scheduleDirty"
            :loading="savingSchedule"
            @click="saveSchedule"
          >
            Save
          </Button>
        </CardHeader>
        <CardContent class="space-y-4 p-4 pt-0">
          <div class="grid gap-3 md:grid-cols-2">
            <div class="space-y-1.5">
              <Label>Trigger</Label>
              <Select :model-value="scheduleMode" @update:model-value="scheduleMode = $event as ScheduleMode">
                <SelectTrigger class="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="o in SCHEDULE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div class="space-y-1.5">
              <Label>Compute dial</Label>
              <Select :model-value="dial" @update:model-value="dial = $event as ComputeDial">
                <SelectTrigger class="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="o in DIAL_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div v-if="scheduleMode === 'cron'" class="space-y-1.5">
            <Label>Crontab (5 fields, UTC)</Label>
            <Input v-model="cronExpr" placeholder="0 2 * * *" class="font-mono" />
            <div class="flex flex-wrap gap-1.5 pt-0.5">
              <Button
                v-for="preset in CRON_PRESETS"
                :key="preset.expr"
                variant="outline"
                size="sm"
                @click="cronExpr = preset.expr"
              >
                {{ preset.label }}
              </Button>
            </div>
          </div>
          <p class="text-xs text-muted-foreground">
            <template v-if="inv.job_type === 'audit-stale'">
              Each due tick audits the stalest / never-checked documentation pages
              (up to {{ auditLimit }} per tick, one scoped run each). “Disabled” on the
              compute dial is the kill switch even with a cron set.
            </template>
            <template v-else>
              Cron runs dispatch on the beat scanner; on-push runs are gated by the compute
              dial — “auto-run on free compute” makes them cost nothing on a local provider.
            </template>
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader class="p-4"><CardTitle class="text-base">Runs</CardTitle></CardHeader>
        <CardContent class="p-0">
          <ul v-if="runs.length" class="stagger-children divide-y px-4">
            <li v-for="r in runs" :key="r.uid" class="py-2 text-sm">
              <span class="font-mono uppercase">{{ r.status }}</span> · {{ r.executor }} ·
              <router-link :to="{ name: 'run-detail', params: { uid: r.uid } }" class="font-mono text-primary hover:underline">{{ r.uid.slice(0, 8) }}</router-link>
              <span v-if="r.error" class="text-destructive"> · {{ r.error }}</span>
            </li>
          </ul>
          <div v-else class="p-4 text-sm text-muted-foreground">No runs yet.</div>
        </CardContent>
      </Card>

      <CommentThread
        subject-type="investigation"
        :subject-uid="inv.uid"
        :repository-uid="inv.repository_uid"
        title="Discussion"
      />
    </template>
  </div>
</template>
