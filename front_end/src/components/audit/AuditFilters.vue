<script setup lang="ts">
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

defineProps<{ subjectFilter: string; kindFilter: string }>()
const emit = defineEmits<{
  'update:subjectFilter': [v: string]
  'update:kindFilter': [v: string]
}>()

const SUBJECT_TYPES = ['Run', 'Finding', 'Doc', 'DocEdit', 'Memory', 'Sandbox', 'Repository']
const KINDS = [
  'finding.created', 'finding.updated',
  'doc.updated', 'doc_edit.proposed', 'doc_edit.resolved', 'memory.written',
  'sandbox.created', 'sandbox.destroyed',
  'run.interrupted', 'run.ended',
  'policy.version_bumped',
]

// SelectItem values cannot be empty — 'all' is the "no filter" sentinel that we
// translate back to '' (the store treats falsy as "no filter").
function onSubject(v: unknown) {
  emit('update:subjectFilter', v === 'all' ? '' : (v as string))
}
function onKind(v: unknown) {
  emit('update:kindFilter', v === 'all' ? '' : (v as string))
}
</script>

<template>
  <div class="flex flex-wrap items-center gap-2">
    <Select
      :model-value="subjectFilter || 'all'"
      @update:model-value="onSubject"
    >
      <SelectTrigger class="w-full sm:w-56">
        <SelectValue placeholder="All subject types" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">All subject types</SelectItem>
        <SelectItem v-for="s in SUBJECT_TYPES" :key="s" :value="s">{{ s }}</SelectItem>
      </SelectContent>
    </Select>
    <Select
      :model-value="kindFilter || 'all'"
      @update:model-value="onKind"
    >
      <SelectTrigger class="w-full sm:w-56">
        <SelectValue placeholder="All kinds" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">All kinds</SelectItem>
        <SelectItem v-for="k in KINDS" :key="k" :value="k">{{ k }}</SelectItem>
      </SelectContent>
    </Select>
  </div>
</template>
