<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { useOrganizationStore } from '@/stores/organizationStore'
import { useCurrentUserStore } from '@/stores/currentUserStore'
import { useGithubAppStore } from '@/stores/githubAppStore'
import { useToast } from '@/composables/useToast'
import type { OrgMemberDTO, RefineFalsePositivePolicy } from '@/types/api'
import { Crown, Github, Mail, Plus, Slack, Trash2, UserMinus } from 'lucide-vue-next'

const org = useOrganizationStore()
const currentUser = useCurrentUserStore()
const github = useGithubAppStore()
const toast = useToast()

/** Org admins (and owners) manage the org's GitHub install + repos. */
const canManageGithub = computed(() => currentUser.isAdmin)

const ROLE_OPTIONS = [
  { label: 'viewer', value: 'viewer' },
  { label: 'maintainer', value: 'maintainer' },
  { label: 'admin', value: 'admin' },
]

// What a `refine` run does when it judges a Finding to be a false positive.
const REFINE_POLICY_OPTIONS = [
  { label: 'Annotate only (leave open)', value: 'annotate' },
  { label: 'Dismiss', value: 'dismiss' },
  { label: 'Mark won’t-fix', value: 'wont-fix' },
]

const loading = ref(true)
const orgName = ref('')
const savingName = ref(false)
const refinePolicy = ref<RefineFalsePositivePolicy>('annotate')
const savingSettings = ref(false)
/** UID of the member whose PATCH is in flight. */
const updatingMember = ref<string | null>(null)
const removeTarget = ref<OrgMemberDTO | null>(null)
const removing = ref(false)
const inviteOpen = ref(false)
const inviteEmail = ref('')
const inviteRole = ref('maintainer')
const inviting = ref(false)
/** UID of the invitation whose DELETE is in flight. */
const revoking = ref<string | null>(null)

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([
      org.fetchOrg(),
      org.fetchMembers(),
      // Org-scoped: returns whether the platform App exists + THIS org's
      // installations + an org-bound install link. Never blocks the page.
      github.fetchStatus().catch(() => {}),
    ])
    orgName.value = org.org?.name ?? ''
    refinePolicy.value = org.org?.settings?.refine_false_positive_policy ?? 'annotate'
    if (currentUser.isOrgOwner) {
      // Owner-only endpoint; the owner default may still hold before /me
      // answers, so a plain member's 403 here is expected — swallow it.
      await org.fetchInvitations().catch(() => {})
    }
  } catch (e: any) {
    toast.error('Load failed', e.detail || e.message)
  } finally {
    loading.value = false
  }
})

function openInstall() {
  // Org-bound install URL: GitHub returns to /api/v1/github/app/setup with a
  // signed state, linking the new installation to THIS org.
  if (github.status.install_url) window.open(github.status.install_url, '_blank')
}

async function saveName() {
  savingName.value = true
  try {
    await org.rename(orgName.value.trim())
    toast.success('Organization renamed')
  } catch (e: any) {
    toast.error('Rename failed', e.detail || e.message)
  } finally {
    savingName.value = false
  }
}

async function saveRefinePolicy(policy: string) {
  const next = policy as RefineFalsePositivePolicy
  const prev = refinePolicy.value
  refinePolicy.value = next
  savingSettings.value = true
  try {
    await org.updateSettings({ refine_false_positive_policy: next })
    toast.success('Refine policy saved')
  } catch (e: any) {
    refinePolicy.value = prev
    toast.error('Save failed', e.detail || e.message)
  } finally {
    savingSettings.value = false
  }
}

async function onRoleChange(m: OrgMemberDTO, role: string) {
  updatingMember.value = m.uid
  try {
    await org.updateMember(m.uid, { role: role as OrgMemberDTO['role'] })
    toast.success('Role updated', m.email)
  } catch (e: any) {
    toast.error('Update failed', e.detail || e.message)
  } finally {
    updatingMember.value = null
  }
}

async function toggleOwner(m: OrgMemberDTO) {
  updatingMember.value = m.uid
  try {
    const next = m.org_role === 'owner' ? 'member' : 'owner'
    await org.updateMember(m.uid, { org_role: next })
    toast.success(next === 'owner' ? 'Owner added' : 'Owner removed', m.email)
  } catch (e: any) {
    // Backend 409s when demoting the last owner — surface its detail.
    toast.error('Update failed', e.detail || e.message)
  } finally {
    updatingMember.value = null
  }
}

async function confirmRemove() {
  if (!removeTarget.value) return
  removing.value = true
  try {
    await org.removeMember(removeTarget.value.uid)
    toast.success('Member removed', removeTarget.value.email)
    removeTarget.value = null
  } catch (e: any) {
    toast.error('Remove failed', e.detail || e.message)
  } finally {
    removing.value = false
  }
}

async function sendInvite() {
  inviting.value = true
  try {
    await org.invite(inviteEmail.value.trim(), inviteRole.value as OrgMemberDTO['role'])
    toast.success('Invitation sent', inviteEmail.value.trim())
    inviteOpen.value = false
    inviteEmail.value = ''
    inviteRole.value = 'maintainer'
  } catch (e: any) {
    // 409 = duplicate invite or already a member — backend detail says which.
    toast.error('Invite failed', e.detail || e.message)
  } finally {
    inviting.value = false
  }
}

async function revoke(uid: string) {
  revoking.value = uid
  try {
    await org.revokeInvitation(uid)
    toast.success('Invitation revoked')
  } catch (e: any) {
    toast.error('Revoke failed', e.detail || e.message)
  } finally {
    revoking.value = null
  }
}
</script>

<template>
  <div class="space-y-6 max-w-3xl">
    <PageHeader
      :title="org.org?.name || 'Organization'"
      subtitle="Members, roles and invitations for your organization."
    />

    <Card>
      <CardHeader>
        <CardTitle class="text-base">Organization</CardTitle>
      </CardHeader>
      <CardContent>
        <Skeleton v-if="loading" class="h-16" />
        <div v-else class="space-y-2">
          <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input v-model="orgName" placeholder="Organization name" :disabled="!currentUser.isOrgOwner" />
            <Button
              class="shrink-0"
              :loading="savingName"
              :disabled="!currentUser.isOrgOwner || !orgName.trim()"
              @click="saveName"
            >
              Save
            </Button>
          </div>
          <div class="text-xs text-muted-foreground">
            {{ org.org?.member_count ?? 0 }} {{ (org.org?.member_count ?? 0) === 1 ? 'member' : 'members' }}
            · {{ org.org?.repository_count ?? 0 }} {{ (org.org?.repository_count ?? 0) === 1 ? 'repository' : 'repositories' }}
          </div>
        </div>
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <CardTitle class="text-base">Refine runs</CardTitle>
      </CardHeader>
      <CardContent>
        <Skeleton v-if="loading" class="h-16" />
        <div v-else class="space-y-2">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div class="min-w-0">
              <div class="text-sm font-medium">False-positive policy</div>
              <p class="text-xs text-muted-foreground">
                What a refine run does when it decides a finding isn’t a real issue.
              </p>
            </div>
            <Select
              :model-value="refinePolicy"
              :disabled="!currentUser.isOrgOwner || savingSettings"
              @update:model-value="saveRefinePolicy($event as string)"
            >
              <SelectTrigger class="w-full sm:w-56 shrink-0">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="o in REFINE_POLICY_OPTIONS" :key="o.value" :value="o.value">
                  {{ o.label }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
          <p v-if="!currentUser.isOrgOwner" class="text-xs text-muted-foreground">
            Only an organization owner can change this.
          </p>
        </div>
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <div class="flex items-center justify-between gap-2">
          <CardTitle class="text-base flex items-center gap-2">
            <Github class="h-4 w-4" /> GitHub
          </CardTitle>
          <Badge
            v-if="github.status.installations.length || github.status.pat_connections?.length"
            variant="success"
            class="px-1.5 text-[10px]"
          >connected</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <Skeleton v-if="loading" class="h-16" />

        <!-- Nothing connected yet: paste a token, or install the App if set up. -->
        <div v-else-if="!github.status.connected" class="text-sm text-muted-foreground space-y-2">
          <p>
            GitHub isn't connected yet. Add a fine-grained access token under
            Settings → GitHub — or install the platform's GitHub App once your
            OpenSweep operator has set it up.
          </p>
          <RouterLink to="/settings/github">
            <Button variant="outline" size="sm"><Github /> Set up GitHub</Button>
          </RouterLink>
        </div>

        <!-- Connected via token and/or App installations. -->
        <div v-else class="space-y-3">
          <div v-if="github.status.pat_connections?.length" class="space-y-2">
            <p class="text-xs text-muted-foreground">This organization's access tokens:</p>
            <div
              v-for="conn in github.status.pat_connections"
              :key="conn.uid"
              class="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
            >
              <span class="font-medium">{{ conn.account || 'access token' }}</span>
              <span class="text-xs text-muted-foreground">token</span>
            </div>
          </div>
          <div v-if="github.status.installations.length" class="space-y-2">
            <p class="text-xs text-muted-foreground">This organization's GitHub installations:</p>
            <div
              v-for="inst in github.status.installations"
              :key="inst.id"
              class="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
            >
              <span class="font-medium">{{ inst.account }}</span>
              <span class="text-xs text-muted-foreground">
                {{ inst.repos_count ?? 0 }} {{ inst.repos_count === 1 ? 'repo' : 'repos' }} accessible
              </span>
            </div>
          </div>
          <p
            v-if="!github.status.installations.length && !github.status.pat_connections?.length"
            class="text-sm text-muted-foreground"
          >
            The GitHub App is available. Install it on your GitHub account or organization to
            grant OpenSweep access to your repositories.
          </p>

          <div v-if="canManageGithub" class="flex flex-wrap items-center gap-2">
            <Button
              v-if="github.status.install_url"
              variant="outline"
              size="sm"
              @click="openInstall"
            >
              <Github />
              {{ github.status.installations.length ? 'Manage installation' : 'Install on GitHub' }}
            </Button>
            <RouterLink :to="{ path: '/repositories', query: { connect: '1' } }">
              <Button size="sm">Connect a repository</Button>
            </RouterLink>
          </div>
          <p v-else class="text-xs text-muted-foreground">
            An organization admin can install the App and connect repositories.
          </p>
        </div>
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <CardTitle class="text-base flex items-center gap-2">
          <Slack class="h-4 w-4" /> Slack
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p class="text-sm text-muted-foreground">
            Route findings, run and PR notifications to Slack channels — and ask Koala questions from Slack.
          </p>
          <RouterLink to="/settings/slack" class="shrink-0">
            <Button variant="outline" size="sm"><Slack /> Slack notifications</Button>
          </RouterLink>
        </div>
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <div class="flex items-center justify-between gap-2">
          <CardTitle class="text-base">Members</CardTitle>
          <span class="text-xs text-muted-foreground">{{ org.members.length }}</span>
        </div>
      </CardHeader>
      <CardContent>
        <div v-if="loading" class="space-y-2">
          <Skeleton v-for="i in 3" :key="i" class="h-12" />
        </div>
        <div v-else class="stagger-children space-y-2">
          <div
            v-for="m in org.members"
            :key="m.uid"
            class="flex flex-col gap-3 rounded-md border px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
          >
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span class="truncate text-sm font-medium">{{ m.email }}</span>
                <Badge v-if="m.org_role === 'owner'" variant="info" class="px-1.5 text-[10px]">
                  <Crown class="h-3 w-3" /> owner
                </Badge>
              </div>
              <div class="mt-0.5 truncate text-xs text-muted-foreground">{{ m.display_name }}</div>
            </div>
            <div v-if="currentUser.isOrgOwner" class="flex flex-wrap items-center gap-2 shrink-0">
              <Select
                :model-value="m.role"
                :disabled="updatingMember === m.uid"
                @update:model-value="onRoleChange(m, $event as string)"
              >
                <SelectTrigger class="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="o in ROLE_OPTIONS" :key="o.value" :value="o.value">
                    {{ o.label }}
                  </SelectItem>
                </SelectContent>
              </Select>
              <Button
                size="sm"
                variant="outline"
                :loading="updatingMember === m.uid"
                @click="toggleOwner(m)"
              >
                {{ m.org_role === 'owner' ? 'Remove owner' : 'Make owner' }}
              </Button>
              <Button size="sm" variant="ghost" class="text-destructive" @click="removeTarget = m">
                <UserMinus />
              </Button>
            </div>
            <Badge v-else variant="outline" class="shrink-0 px-1.5 text-[10px]">{{ m.role }}</Badge>
          </div>
        </div>
      </CardContent>
    </Card>

    <Card v-if="currentUser.isOrgOwner">
      <CardHeader>
        <div class="flex items-center justify-between gap-2">
          <CardTitle class="text-base">Pending invitations</CardTitle>
          <Button size="sm" @click="inviteOpen = true">
            <Plus /> Invite member
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div v-if="loading" class="space-y-2">
          <Skeleton v-for="i in 2" :key="i" class="h-12" />
        </div>
        <EmptyState
          v-else-if="!org.invitations.length"
          :icon="Mail"
          title="No pending invitations"
          description="Invite teammates by email — they accept from their Account page and join this organization."
          class="border-0 py-8"
        />
        <div v-else class="space-y-2">
          <div
            v-for="inv in org.invitations"
            :key="inv.uid"
            class="flex items-center justify-between gap-3 rounded-md border px-3 py-2"
          >
            <div class="flex items-center gap-2 min-w-0">
              <Mail class="h-4 w-4 text-muted-foreground shrink-0" />
              <span class="truncate text-sm font-medium">{{ inv.email }}</span>
              <Badge variant="outline" class="px-1.5 text-[10px]">{{ inv.role }}</Badge>
              <span v-if="inv.created_at" class="text-xs text-muted-foreground">{{ inv.created_at.slice(0, 10) }}</span>
            </div>
            <Button
              size="sm"
              variant="ghost"
              class="text-destructive shrink-0"
              :loading="revoking === inv.uid"
              @click="revoke(inv.uid)"
            >
              <Trash2 />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- Remove-member confirm -->
    <Dialog :open="removeTarget !== null" @update:open="removeTarget = null">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Remove member</DialogTitle>
          <DialogDescription>
            {{ removeTarget?.email ?? '' }} loses access to this organization and gets a fresh organization of their own.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" @click="removeTarget = null">Cancel</Button>
          <Button variant="destructive" :loading="removing" @click="confirmRemove">
            <UserMinus /> Remove member
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Invite member -->
    <Dialog v-model:open="inviteOpen">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Invite member</DialogTitle>
          <DialogDescription>
            Invite a teammate by email. They accept from their Account page and join this organization.
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-3">
          <div class="space-y-1.5">
            <Label for="invite-email">Email</Label>
            <Input id="invite-email" v-model="inviteEmail" type="email" placeholder="teammate@example.com" />
          </div>
          <div class="space-y-1.5">
            <Label for="invite-role">Role</Label>
            <Select v-model="inviteRole">
              <SelectTrigger id="invite-role" class="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="o in ROLE_OPTIONS" :key="o.value" :value="o.value">
                  {{ o.label }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" @click="inviteOpen = false">Cancel</Button>
          <Button :loading="inviting" :disabled="!inviteEmail.trim()" @click="sendInvite">
            <Plus /> Send invite
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
