<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import AppSidebar from '@/components/shell/AppSidebar.vue'
import Topbar from '@/components/shell/Topbar.vue'
import ProviderSetupBanner from '@/components/shell/ProviderSetupBanner.vue'
import BackendUnavailableBanner from '@/components/shell/BackendUnavailableBanner.vue'
import RouteProgress from '@/components/shell/RouteProgress.vue'
import CommandPalette from '@/components/shell/CommandPalette.vue'
import OpenSweepChatWidget from '@/components/opensweep/OpenSweepChatWidget.vue'
import { Toaster } from '@/components/ui/sonner'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { ErrorState } from '@/components/ui/error-state'
import { Button } from '@/components/ui/button'
import { useCurrentRepo } from '@/composables/useCurrentRepo'
import { startRunNotifications, stopRunNotifications } from '@/composables/useRunNotifications'

// Org-wide run finished/failed/paused toasts + chimes, on every page.
onMounted(startRunNotifications)
onBeforeUnmount(stopRunNotifications)

// Repo-scoped routes (/r/:repoSlug/...) show an infinite skeleton when the
// slug doesn't resolve — surface the resolution error once, centrally, for
// every consumer of useCurrentRepo.
const { slug, error: repoError, retry } = useCurrentRepo()

const repoErrorMessage = computed(() => {
  if (!slug.value || !repoError.value) return null
  const e = repoError.value
  return e instanceof Error ? e.message : String(e)
})
</script>

<template>
  <SidebarProvider>
    <AppSidebar />
    <SidebarInset
      class="min-w-0 h-svh overflow-hidden md:peer-data-[variant=inset]:h-[calc(100svh-1rem)] md:peer-data-[variant=inset]:border"
    >
      <RouteProgress />
      <Topbar />
      <BackendUnavailableBanner />
      <ProviderSetupBanner />
      <section class="min-h-0 flex-1 overflow-auto">
        <router-view v-slot="{ Component }">
          <transition
            enter-active-class="transition duration-200 ease-out"
            enter-from-class="opacity-0 translate-y-1"
            enter-to-class="opacity-100 translate-y-0"
            mode="out-in"
          >
            <div class="mx-auto w-full max-w-7xl p-4 sm:p-6 lg:p-8">
              <ErrorState
                v-if="repoErrorMessage"
                title="Couldn't load workspace"
                :message="`Workspace “${slug}” didn't resolve: ${repoErrorMessage}`"
              >
                <Button variant="outline" size="sm" @click="retry">Retry</Button>
              </ErrorState>
              <component :is="Component" v-else />
            </div>
          </transition>
        </router-view>
      </section>
    </SidebarInset>
    <Toaster :rich-colors="true" close-button />
    <CommandPalette />
    <OpenSweepChatWidget />
  </SidebarProvider>
</template>
