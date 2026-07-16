import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { apiGet, apiPatch, apiPost } from '@/services/api'
import type { MeDTO, MeProfileDTO } from '@/types/api'

/**
 * Current-user store.
 *
 * Defaults to the hardcoded local user (uid 'local-user', matches back_end's
 * LOCAL_USER_UID) so "mine only" filters work before /me answers — and
 * indefinitely when auth is disabled. With Zitadel configured, load()
 * (called from the router guard) replaces it with the real user + role.
 * Org defaults (owner + platform admin + onboarded) match local mode so
 * nothing flashes hidden before /me answers.
 */
export const useCurrentUserStore = defineStore('currentUser', () => {
  const uid = ref<string>('local-user')
  const email = ref<string>('')
  const displayName = ref<string>('Local User')
  const role = ref<'viewer' | 'maintainer' | 'admin'>('admin')
  const orgUid = ref<string>('')
  const orgRole = ref<'owner' | 'member'>('owner')
  const platformAdmin = ref(true)
  const onboarded = ref(true)
  const loaded = ref(false)
  const profile = ref<MeProfileDTO | null>(null)

  function applyMe(me: MeDTO) {
    uid.value = me.uid
    email.value = me.email
    displayName.value = me.display_name
    role.value = me.role
    orgUid.value = me.org_uid
    orgRole.value = me.org_role
    platformAdmin.value = me.is_platform_admin
    onboarded.value = me.onboarded
  }

  async function load() {
    if (loaded.value) return
    loaded.value = true // one in-flight attempt; reset on failure below
    try {
      applyMe(await apiGet<MeDTO>('/me'))
    } catch {
      loaded.value = false // backend unreachable — retry on next navigation
    }
  }

  /** GET /me/profile — org + pending invitations; cached on the store. */
  async function loadProfile(): Promise<MeProfileDTO> {
    profile.value = await apiGet<MeProfileDTO>('/me/profile')
    return profile.value
  }

  async function updateProfile(newDisplayName: string): Promise<void> {
    const me = await apiPatch<MeDTO>('/me', { display_name: newDisplayName })
    applyMe(me)
    if (profile.value) profile.value = { ...profile.value, display_name: me.display_name }
  }

  async function setOnboarded(v: boolean): Promise<void> {
    const me = await apiPatch<MeDTO>('/me', { onboarded: v })
    applyMe(me)
    if (profile.value) profile.value = { ...profile.value, onboarded: me.onboarded }
  }

  /** Accept an org invitation, then force-reload /me + profile — the accept
   *  moves this user into the inviting org. */
  async function acceptInvitation(invitationUid: string): Promise<void> {
    const me = await apiPost<MeDTO>(`/me/invitations/${invitationUid}/accept`)
    applyMe(me)
    await loadProfile()
  }

  const mineOnlyFilter = computed(() => uid.value)
  const isMaintainer = computed(() => role.value === 'maintainer' || role.value === 'admin')
  const isAdmin = computed(() => role.value === 'admin')
  const isOrgOwner = computed(() => orgRole.value === 'owner')
  const isPlatformAdmin = computed(() => platformAdmin.value)

  return {
    uid, email, displayName, role, orgUid, orgRole, onboarded, loaded, profile,
    load, loadProfile, updateProfile, setOnboarded, acceptInvitation,
    mineOnlyFilter, isMaintainer, isAdmin, isOrgOwner, isPlatformAdmin,
  }
})
