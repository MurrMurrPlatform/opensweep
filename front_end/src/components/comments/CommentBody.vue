<script setup lang="ts">
import { computed } from 'vue'
import { MENTION_ROUTES, parseMentionSegments } from '@/lib/mentions'

/** Comment body renderer: plain text with @opensweep highlights and data-item
 *  mention chips (linked to the item's detail view when one exists). */
const props = defineProps<{ body: string }>()

const segments = computed(() => parseMentionSegments(props.body))

function routeFor(segment: { type?: string; uid?: string }) {
  const name = segment.type ? MENTION_ROUTES[segment.type as keyof typeof MENTION_ROUTES] : undefined
  return name && segment.uid ? { name, params: { uid: segment.uid } } : null
}
</script>

<template>
  <p class="text-sm whitespace-pre-wrap break-words leading-relaxed">
    <template v-for="(segment, i) in segments" :key="i">
      <span
        v-if="segment.kind === 'opensweep'"
        class="inline-flex items-center rounded bg-primary/15 px-1 font-medium text-primary"
        >{{ segment.text }}</span
      >
      <RouterLink
        v-else-if="segment.kind === 'item' && routeFor(segment)"
        :to="routeFor(segment)!"
        class="inline-flex items-center rounded bg-muted px-1 font-medium text-foreground hover:underline"
        >@{{ segment.text }}</RouterLink
      >
      <span
        v-else-if="segment.kind === 'item'"
        class="inline-flex items-center rounded bg-muted px-1 font-medium text-foreground"
        >@{{ segment.text }}</span
      >
      <template v-else>{{ segment.text }}</template>
    </template>
  </p>
</template>
