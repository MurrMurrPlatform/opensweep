<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Bot, X } from 'lucide-vue-next'
import { useRunSocket } from '@/composables/useRunSocket'
import { useCurrentUserStore } from '@/stores/currentUserStore'
import { activityLabel } from '@/lib/opensweepActivity'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import type { RunStatus } from '@/types/api'

/**
 * Live "OpenSweep is working…" bubble at the tail of a comment thread while an
 * @opensweep reply run is in flight. Watches the run read-only over the run WS
 * (viewer sockets never interrupt turns) and peeks at tool activity.
 *
 * - reply posted (opensweep_platform_add_comment) → emit 'replied'
 * - terminal status without a reply → inline failure note, emit 'settled'
 * - socket unavailable → emit 'unavailable' so the thread falls back to polling
 */
const props = defineProps<{ runUid: string }>()
const emit = defineEmits<{
  replied: []
  settled: []
  unavailable: []
  dismiss: []
}>()

const currentUser = useCurrentUserStore()
const activity = ref('reading your comment…')
const failed = ref(false)
const replySeen = ref(false)

const TERMINAL: RunStatus[] = ['awaiting_input', 'ended', 'failed', 'cancelled', 'limit_exceeded']

const socket = useRunSocket(props.runUid, {
  onEvent(event) {
    // tool_use is appended BEFORE the tool executes — only the (non-error)
    // tool_result proves the reply comment actually exists.
    if (
      event.type === 'tool_result' &&
      event.name === 'opensweep_platform_add_comment' &&
      !event.is_error
    ) {
      if (!replySeen.value) {
        replySeen.value = true
        emit('replied')
      }
      return
    }
    const label = activityLabel(event)
    if (label && !failed.value) activity.value = label
  },
  onStatus(status) {
    if (!TERMINAL.includes(status)) return
    if (replySeen.value) return // parent already reloading; it removes us
    failed.value = true
    emit('settled')
  },
  onUnavailable() {
    emit('unavailable')
  },
  onUnauthorized() {
    // Run gone or auth lost — nothing to watch; the poll fallback decides.
    emit('unavailable')
  },
})

onMounted(() => socket.connect())
</script>

<template>
  <li class="-mx-2 flex gap-3 rounded-lg bg-primary/5 p-2">
    <Avatar class="mt-0.5 size-8 shrink-0">
      <AvatarFallback class="bg-primary/15 text-primary">
        <Bot class="size-4" :class="failed ? '' : 'animate-pulse'" />
      </AvatarFallback>
    </Avatar>
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2 text-xs">
        <span class="font-medium text-primary">OpenSweep</span>
        <RouterLink
          v-if="currentUser.isPlatformAdmin"
          :to="{ name: 'run-detail', params: { uid: runUid } }"
          class="text-muted-foreground hover:underline"
        >view run</RouterLink>
        <button
          v-if="failed"
          type="button"
          class="ml-auto text-muted-foreground transition-colors hover:text-foreground"
          title="Dismiss"
          @click="emit('dismiss')"
        >
          <X class="size-3.5" />
        </button>
      </div>
      <div v-if="failed" class="mt-1 text-sm text-muted-foreground">
        OpenSweep couldn’t reply to this thread — the run finished without posting a comment.
      </div>
      <div v-else class="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
        <span class="inline-flex gap-0.5">
          <span class="size-1 animate-bounce rounded-full bg-primary [animation-delay:0ms]" />
          <span class="size-1 animate-bounce rounded-full bg-primary [animation-delay:150ms]" />
          <span class="size-1 animate-bounce rounded-full bg-primary [animation-delay:300ms]" />
        </span>
        <span class="italic">{{ activity }}</span>
      </div>
    </div>
  </li>
</template>
