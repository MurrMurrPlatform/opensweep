import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiDelete, apiGet, apiPatch, apiPost } from '@/services/api'
import type { OrganizationDTO, OrgInvitationDTO, OrgMemberDTO, OrgSettingsDTO } from '@/types/api'

export const useOrganizationStore = defineStore('organization', () => {
  const org = ref<OrganizationDTO | null>(null)
  const members = ref<OrgMemberDTO[]>([])
  const membersLoaded = ref(false)
  const invitations = ref<OrgInvitationDTO[]>([])
  const invitationsLoaded = ref(false)

  async function fetchOrg(): Promise<OrganizationDTO> {
    org.value = await apiGet<OrganizationDTO>('/org')
    return org.value
  }

  async function rename(name: string): Promise<OrganizationDTO> {
    org.value = await apiPatch<OrganizationDTO>('/org', { name })
    return org.value
  }

  async function updateSettings(settings: OrgSettingsDTO): Promise<OrganizationDTO> {
    org.value = await apiPatch<OrganizationDTO>('/org', { settings })
    return org.value
  }

  async function fetchMembers(): Promise<OrgMemberDTO[]> {
    members.value = await apiGet<OrgMemberDTO[]>('/org/members')
    membersLoaded.value = true
    return members.value
  }

  async function updateMember(uid: string, patch: Partial<Pick<OrgMemberDTO, 'role' | 'org_role'>>): Promise<OrgMemberDTO> {
    const m = await apiPatch<OrgMemberDTO>(`/org/members/${uid}`, patch)
    members.value = members.value.map(x => (x.uid === uid ? m : x))
    return m
  }

  async function removeMember(uid: string): Promise<void> {
    await apiDelete(`/org/members/${uid}`)
    members.value = members.value.filter(x => x.uid !== uid)
  }

  async function fetchInvitations(): Promise<OrgInvitationDTO[]> {
    invitations.value = await apiGet<OrgInvitationDTO[]>('/org/invitations')
    invitationsLoaded.value = true
    return invitations.value
  }

  async function invite(email: string, role: OrgInvitationDTO['role']): Promise<OrgInvitationDTO> {
    const inv = await apiPost<OrgInvitationDTO>('/org/invitations', { email, role })
    invitations.value = [...invitations.value, inv]
    return inv
  }

  async function revokeInvitation(uid: string): Promise<void> {
    await apiDelete(`/org/invitations/${uid}`)
    invitations.value = invitations.value.filter(x => x.uid !== uid)
  }

  return {
    org, members, membersLoaded, invitations, invitationsLoaded,
    fetchOrg, rename, updateSettings, fetchMembers, updateMember, removeMember,
    fetchInvitations, invite, revokeInvitation,
  }
})
