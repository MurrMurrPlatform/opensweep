<script setup lang="ts">
// Org-wide readiness strip: runs can't start without an LLM provider, so
// surface that on every page until one is configured. No dismiss — the store
// refreshes status after provider mutations, which hides the banner.
import { computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useLLMProviderStore } from '@/stores/llmProviderStore'
import { useCurrentUserStore } from '@/stores/currentUserStore'
import { AlertTriangle } from 'lucide-vue-next'

const store = useLLMProviderStore()
const currentUser = useCurrentUserStore()

onMounted(() => {
  // Swallow failure — unknown status renders nothing.
  store.fetchStatus().catch(() => {})
})

// The onboarding wizard renders outside this shell, so no /welcome check needed.
const visible = computed(() =>
  currentUser.loaded
  && store.status !== null
  && !store.status.configured,
)
</script>

<template>
  <div
    v-if="visible"
    class="border-b border-warn/30 bg-warn/10 px-4 py-2 text-sm sm:px-6 lg:px-8"
  >
    <div class="mx-auto flex w-full max-w-7xl flex-wrap items-center gap-x-3 gap-y-1">
      <span class="flex items-center gap-1.5 font-medium text-warn">
        <AlertTriangle class="h-4 w-4 shrink-0" />
        No LLM provider configured — runs can't start until your organization adds one.
      </span>
      <RouterLink
        v-if="currentUser.isAdmin"
        to="/admin/llm-providers"
        class="font-medium text-primary underline underline-offset-2 hover:opacity-80"
      >
        Configure provider
      </RouterLink>
      <span v-else class="text-muted-foreground">
        Ask an organization admin to configure one in Settings → LLM providers.
      </span>
    </div>
  </div>
</template>
