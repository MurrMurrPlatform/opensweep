<script setup lang="ts">
// Shown when /me failed: the shell renders with fail-closed viewer defaults
// and any data on screen is from before the outage, so say so instead of
// letting the app look healthy. load() resets on failure, so Retry re-fetches.
import { ref } from 'vue'
import { AlertTriangle } from 'lucide-vue-next'
import { useCurrentUserStore } from '@/stores/currentUserStore'

const currentUser = useCurrentUserStore()
const retrying = ref(false)

async function retry() {
  retrying.value = true
  try {
    await currentUser.load()
  } finally {
    retrying.value = false
  }
}
</script>

<template>
  <div
    v-if="currentUser.loadFailed"
    class="border-b border-destructive/30 bg-destructive/10 px-4 py-2 text-sm sm:px-6 lg:px-8"
  >
    <div class="mx-auto flex w-full max-w-7xl flex-wrap items-center gap-x-3 gap-y-1">
      <span class="flex items-center gap-1.5 font-medium text-destructive">
        <AlertTriangle class="h-4 w-4 shrink-0" />
        Can't reach the OpenSweep backend — what you see may be stale, and actions will fail.
      </span>
      <button
        type="button"
        class="font-medium text-primary underline underline-offset-2 hover:opacity-80 disabled:opacity-50"
        :disabled="retrying"
        @click="retry"
      >
        {{ retrying ? 'Retrying…' : 'Retry' }}
      </button>
    </div>
  </div>
</template>
