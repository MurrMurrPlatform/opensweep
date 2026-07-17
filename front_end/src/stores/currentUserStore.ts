import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { apiGet, apiPatch, apiPost } from '@/services/api'
import type { MeDTO, MeProfileDTO } from '@/types/api'

/**
 * Current-user store.
 *
 * Defaults are FAIL-CLOSED: least-privileged role until /me answers. The
 * router guard awaits load() before the first app navigation, so real users
 * never see the defaults — they only render when /me itself fails, and a
 * broken backend must not present anyone as admin/owner/platform-admin.
 * uid keeps the 'local-user' placeholder (back_end's LOCAL_USER_UID) so
 * "mine only" filters stay inert rather than matching a real user.
 */
export const useCurrentUserStore = defineStore('currentUser', () => {
  const uid = ref<string>('local-user')
  const email = ref<string>('')
  const displayName = ref<string>('')
  const role = ref<'viewer' | 'maintainer' | 'admin'>('viewer')
  const orgUid = ref<string>('')
  const orgRole = ref<'owner' | 'member'>('member')
  const platformAdmin = ref(false)
  const onboarded = ref(true)
  const loading = ref(false) // in-flight guard; `loaded` means success only
  const loaded = ref(false)
  const loadFailed = ref(false)
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
    if (loaded.value || loading.value) return
    loading.value = true
    try {
      applyMe(await apiGet<MeDTO>('/me'))
      loaded.value = true
      loadFailed.value = false
    } catch {
      // backend unreachable — retried on next navigation / banner Retry
      loadFailed.value = true // shell shows the backend-unavailable banner
    } finally {
      loading.value = false
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
    uid, email, displayName, role, orgUid, orgRole, onboarded, loaded, loadFailed, profile,
    load, loadProfile, updateProfile, setOnboarded, acceptInvitation,
    mineOnlyFilter, isMaintainer, isAdmin, isOrgOwner, isPlatformAdmin,
  }
})
