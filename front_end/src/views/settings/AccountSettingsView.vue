<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useCurrentUserStore } from '@/stores/currentUserStore'
import { useRepositoryStore } from '@/stores/repositoryStore'
import { useToast } from '@/composables/useToast'
import type { MyInvitationDTO } from '@/types/api'
import { Mail } from 'lucide-vue-next'

const currentUser = useCurrentUserStore()
const repos = useRepositoryStore()
const toast = useToast()
const router = useRouter()

const loading = ref(true)
const displayName = ref('')
const saving = ref(false)
/** UID of the invitation whose accept POST is in flight. */
const accepting = ref<string | null>(null)

onMounted(async () => {
  try {
    await currentUser.loadProfile()
  } catch (e: any) {
    toast.error('Profile fetch failed', e.detail || e.message)
  } finally {
    displayName.value = currentUser.displayName
    loading.value = false
  }
})

async function saveProfile() {
  saving.value = true
  try {
    await currentUser.updateProfile(displayName.value.trim())
    toast.success('Profile updated')
  } catch (e: any) {
    toast.error('Save failed', e.detail || e.message)
  } finally {
    saving.value = false
  }
}

async function accept(inv: MyInvitationDTO) {
  accepting.value = inv.uid
  try {
    await currentUser.acceptInvitation(inv.uid)
    toast.success(`Joined ${inv.org_name}`)
    await repos.fetchAll()
    router.push('/repositories')
  } catch (e: any) {
    toast.error('Accept failed', e.detail || e.message)
  } finally {
    accepting.value = null
  }
}
</script>

<template>
  <div class="space-y-6 max-w-3xl">
    <PageHeader
      title="Account"
      subtitle="Your profile and pending organization invitations."
    />

    <Card>
      <CardHeader>
        <div class="flex flex-wrap items-center justify-between gap-2">
          <CardTitle class="text-base">Profile</CardTitle>
          <div class="flex items-center gap-1.5">
            <Badge variant="outline" class="px-1.5 text-[10px]">{{ currentUser.role }}</Badge>
            <Badge variant="outline" class="px-1.5 text-[10px]">{{ currentUser.orgRole }}</Badge>
            <Badge v-if="currentUser.isPlatformAdmin" variant="info" class="px-1.5 text-[10px]">Platform admin</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <Skeleton v-if="loading" class="h-24" />
        <div v-else class="space-y-4">
          <div class="space-y-1.5">
            <Label for="display-name">Display name</Label>
            <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Input id="display-name" v-model="displayName" placeholder="Your name" />
              <Button
                class="shrink-0"
                :loading="saving"
                :disabled="!displayName.trim()"
                @click="saveProfile"
              >
                Save
              </Button>
            </div>
          </div>
          <div class="space-y-1.5">
            <Label for="email">Email</Label>
            <Input id="email" :model-value="currentUser.email" disabled />
          </div>
        </div>
      </CardContent>
    </Card>

    <Card v-if="currentUser.profile?.pending_invitations.length">
      <CardHeader>
        <div class="flex items-center justify-between gap-2">
          <CardTitle class="text-base">Organization invitations</CardTitle>
          <span class="text-xs text-muted-foreground">{{ currentUser.profile.pending_invitations.length }}</span>
        </div>
      </CardHeader>
      <CardContent>
        <div class="stagger-children space-y-2">
          <div
            v-for="inv in currentUser.profile.pending_invitations"
            :key="inv.uid"
            class="flex items-center justify-between gap-3 rounded-md border px-3 py-2"
          >
            <div class="flex items-center gap-2 min-w-0">
              <Mail class="h-4 w-4 text-muted-foreground shrink-0" />
              <span class="truncate text-sm font-medium">{{ inv.org_name }}</span>
              <Badge variant="outline" class="px-1.5 text-[10px]">{{ inv.role }}</Badge>
            </div>
            <Button
              size="sm"
              :loading="accepting === inv.uid"
              :disabled="accepting !== null && accepting !== inv.uid"
              @click="accept(inv)"
            >
              Accept
            </Button>
          </div>
        </div>
        <p class="mt-3 text-xs text-muted-foreground">
          Accepting moves you into that organization — you leave your current one.
        </p>
      </CardContent>
    </Card>
  </div>
</template>
