<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { buildCron, cronShape, describeCron, parseCron, WEEKDAYS } from '@/lib/cron'

/** Human-friendly crontab builder: frequency + time selects that compose the
 *  5-field expression, with an "Advanced" escape hatch for raw cron. The
 *  v-model stays the crontab string, so callers keep their `cron:<expr>`
 *  trigger contract untouched. */
const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [expr: string] }>()

type Frequency = 'hourly' | 'daily' | 'weekly' | 'monthly' | 'custom'

const frequency = ref<Frequency>('daily')
const everyHours = ref(6)
const weekday = ref(1)
const monthDay = ref(1)
const hour = ref(2)
const minute = ref(0)
const rawExpr = ref('')

const HOUR_INTERVALS = [1, 2, 3, 4, 6, 8, 12]
const MINUTES = [0, 15, 30, 45]
// 1–28 only: every month has them, so a monthly schedule never skips.
const MONTH_DAYS = Array.from({ length: 28 }, (_, i) => i + 1)
const HOURS = Array.from({ length: 24 }, (_, i) => i)

const pad = (n: number) => String(n).padStart(2, '0')

function hydrate(expr: string) {
  rawExpr.value = expr
  const shape = cronShape(expr)
  if (!shape) {
    frequency.value = expr.trim() ? 'custom' : 'daily'
    return
  }
  frequency.value = shape.kind
  if (shape.kind === 'hourly') {
    everyHours.value = HOUR_INTERVALS.includes(shape.everyHours) ? shape.everyHours : 6
    minute.value = shape.minute
    return
  }
  hour.value = shape.hour
  minute.value = MINUTES.includes(shape.minute) ? shape.minute : shape.minute
  if (shape.kind === 'weekly') weekday.value = shape.weekday
  if (shape.kind === 'monthly') monthDay.value = shape.day
}

const builtExpr = computed(() => {
  switch (frequency.value) {
    case 'hourly':
      return buildCron({ kind: 'hourly', everyHours: everyHours.value, minute: minute.value })
    case 'daily':
      return buildCron({ kind: 'daily', hour: hour.value, minute: minute.value })
    case 'weekly':
      return buildCron({ kind: 'weekly', weekday: weekday.value, hour: hour.value, minute: minute.value })
    case 'monthly':
      return buildCron({ kind: 'monthly', day: monthDay.value, hour: hour.value, minute: minute.value })
    case 'custom':
      return rawExpr.value.trim()
  }
  return ''
})

watch(() => props.modelValue, (expr) => {
  if (expr !== builtExpr.value) hydrate(expr)
}, { immediate: true })

// Immediate: an empty v-model picks up the builder's default schedule right
// away, so the parent's save/validation state never sees an empty expr.
watch(builtExpr, (expr) => {
  if (expr !== props.modelValue) emit('update:modelValue', expr)
}, { immediate: true })

const summary = computed(() => describeCron(builtExpr.value))
const customValid = computed(() => parseCron(rawExpr.value) != null)

/** Non-standard minute (hydrated from an existing expr) still needs to show. */
const minuteOptions = computed(() =>
  MINUTES.includes(minute.value) ? MINUTES : [...MINUTES, minute.value].sort((a, b) => a - b),
)
</script>

<template>
  <div class="space-y-2">
    <div class="flex flex-wrap items-end gap-2">
      <div class="space-y-1">
        <Label class="text-xs text-muted-foreground">Repeats</Label>
        <Select
          :model-value="frequency"
          @update:model-value="frequency = $event as Frequency"
        >
          <SelectTrigger class="w-40"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="hourly">Every few hours</SelectItem>
            <SelectItem value="daily">Daily</SelectItem>
            <SelectItem value="weekly">Weekly</SelectItem>
            <SelectItem value="monthly">Monthly</SelectItem>
            <SelectItem value="custom">Custom (cron)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div v-if="frequency === 'hourly'" class="space-y-1">
        <Label class="text-xs text-muted-foreground">Every</Label>
        <Select
          :model-value="String(everyHours)"
          @update:model-value="everyHours = Number($event)"
        >
          <SelectTrigger class="w-32"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem v-for="h in HOUR_INTERVALS" :key="h" :value="String(h)">
              {{ h === 1 ? 'hour' : `${h} hours` }}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div v-if="frequency === 'weekly'" class="space-y-1">
        <Label class="text-xs text-muted-foreground">On</Label>
        <Select
          :model-value="String(weekday)"
          @update:model-value="weekday = Number($event)"
        >
          <SelectTrigger class="w-36"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem v-for="(name, i) in WEEKDAYS" :key="i" :value="String(i)">
              {{ name }}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div v-if="frequency === 'monthly'" class="space-y-1">
        <Label class="text-xs text-muted-foreground">On day</Label>
        <Select
          :model-value="String(monthDay)"
          @update:model-value="monthDay = Number($event)"
        >
          <SelectTrigger class="w-24"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem v-for="d in MONTH_DAYS" :key="d" :value="String(d)">{{ d }}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <template v-if="frequency !== 'custom'">
        <div v-if="frequency !== 'hourly'" class="space-y-1">
          <Label class="text-xs text-muted-foreground">At (UTC)</Label>
          <Select :model-value="String(hour)" @update:model-value="hour = Number($event)">
            <SelectTrigger class="w-24"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="h in HOURS" :key="h" :value="String(h)">{{ pad(h) }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-1">
          <Label class="text-xs text-muted-foreground">{{ frequency === 'hourly' ? 'At minute' : ':' }}</Label>
          <Select :model-value="String(minute)" @update:model-value="minute = Number($event)">
            <SelectTrigger class="w-20"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="m in minuteOptions" :key="m" :value="String(m)">{{ pad(m) }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </template>
    </div>

    <div v-if="frequency === 'custom'" class="space-y-1">
      <Input v-model="rawExpr" placeholder="0 2 * * *" class="w-56 font-mono" />
      <p v-if="rawExpr.trim() && !customValid" class="text-xs text-destructive">
        Needs 5 space-separated fields: minute hour day-of-month month day-of-week.
      </p>
    </div>

    <p class="text-xs text-muted-foreground">
      <template v-if="summary">{{ summary }} · <span class="font-mono">{{ builtExpr }}</span></template>
      <template v-else-if="builtExpr">Crontab (UTC): <span class="font-mono">{{ builtExpr }}</span></template>
      <template v-else>Pick a schedule — times are in UTC.</template>
    </p>
  </div>
</template>
