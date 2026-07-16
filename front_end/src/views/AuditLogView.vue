<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { History } from 'lucide-vue-next'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/ui/page-header'
import { EmptyState } from '@/components/ui/empty-state'
import AuditFilters from '@/components/audit/AuditFilters.vue'
import AuditEventRow from '@/components/audit/AuditEventRow.vue'
import { useAuditStore } from '@/stores/auditStore'

const store = useAuditStore()
const subjectFilter = ref('')
const kindFilter = ref('')

async function refresh() {
  await store.fetchAll({
    subject_type: subjectFilter.value || undefined,
    kind: kindFilter.value || undefined,
    limit: 200,
  })
}

onMounted(refresh)
watch([subjectFilter, kindFilter], refresh)
</script>

<template>
  <div class="flex flex-col gap-4">
    <PageHeader
      title="Audit log"
      subtitle="Every state change is recorded as an :Event node."
    />

    <Card>
      <CardHeader class="p-4">
        <CardTitle class="text-base">Filters</CardTitle>
      </CardHeader>
      <CardContent class="p-4 pt-0">
        <AuditFilters
          v-model:subjectFilter="subjectFilter"
          v-model:kindFilter="kindFilter"
        />
      </CardContent>
    </Card>

    <Card>
      <CardContent class="p-0">
        <div v-if="!store.loaded" class="flex flex-col gap-2 p-4">
          <Skeleton v-for="i in 8" :key="i" class="h-10" />
        </div>
        <div v-else-if="store.list.length" class="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead class="w-[120px]">Time</TableHead>
                <TableHead class="w-[140px]">Subject</TableHead>
                <TableHead>Event</TableHead>
                <TableHead class="text-right">When</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <AuditEventRow v-for="e in store.list" :key="e.uid" :event="e" />
            </TableBody>
          </Table>
        </div>
        <div v-else class="p-4">
          <EmptyState
            :icon="History"
            title="No events match"
            description="Adjust the filters above, or wait for the next state change to be recorded."
            class="border-0"
          />
        </div>
      </CardContent>
    </Card>
  </div>
</template>
