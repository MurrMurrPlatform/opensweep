"""Organization + account management (multi-tenancy).

Everything here is scoped to the caller's own org — there is no cross-org
surface. Org mutations (rename, members, invitations) are owner-only
(api.dependencies.require_org_owner); reading the org and managing one's own
account needs plain authentication.

Membership rules:
  - every org always has ≥1 owner (last-owner demotion/removal is 409)
  - removing a member moves them into a fresh personal org (they lose access
    to this org's data but keep a working account)
  - invitations are matched by email at first login
    (domains/users/services/oidc_user.py) or accepted explicitly via
    /me/invitations by already-registered users.
"""

from fastapi import APIRouter, Depends, HTTPException
from neomodel import adb

from api.dependencies import get_current_user, require_org_owner
from domains.organizations.models import (
    ORG_ROLES,
    Organization,
    OrgInvitation,
)
from domains.organizations.schemas import (
    CreateInvitationRequest,
    MeDTO,
    MyInvitationDTO,
    OrganizationDTO,
    OrgInvitationDTO,
    OrgMemberDTO,
    UpdateMemberRequest,
    UpdateMeRequest,
    UpdateOrganizationRequest,
)
from domains.organizations.services.settings import parse_settings
from domains.organizations.services.provisioning import (
    accept_invitation,
    create_personal_org,
    move_user_to_org,
    org_owner_count,
    pending_invitations_for_email,
)
from domains.users.models import USER_ROLES, User
from domains.users.schemas import UserDTO
from domains.users.services.oidc_user import invalidate_user_cache
from infrastructure.audit import write_audit

router = APIRouter(prefix="/api/v1", tags=["organization"])


async def _get_org(org_uid: str) -> Organization:
    org = await Organization.nodes.get_or_none(uid=org_uid)
    if org is None:
        raise HTTPException(status_code=404, detail="not found")
    return org


async def _org_dto(org: Organization, user: UserDTO) -> OrganizationDTO:
    rows, _ = await adb.cypher_query(
        "MATCH (o:Organization {uid: $org}) "
        "RETURN COUNT { MATCH (u:User {org_uid: $org}) }, "
        "       COUNT { MATCH (r:Repository {org_uid: $org}) }",
        {"org": org.uid},
    )
    members, repos = (int(rows[0][0]), int(rows[0][1])) if rows else (0, 0)
    return OrganizationDTO(
        uid=org.uid,
        name=org.name,
        created_at=org.created_at,
        member_count=members,
        repository_count=repos,
        is_owner=user.org_role == "owner",
        settings=parse_settings(org.settings_json),
    )


def _member_dto(user: User) -> OrgMemberDTO:
    return OrgMemberDTO(
        uid=user.uid,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        org_role=user.org_role,
        created_at=user.created_at,
    )


def _invitation_dto(inv: OrgInvitation) -> OrgInvitationDTO:
    return OrgInvitationDTO(
        uid=inv.uid,
        email=inv.email,
        role=inv.role,
        status=inv.status,
        invited_by=inv.invited_by,
        created_at=inv.created_at,
    )


async def _org_members(org_uid: str) -> list[User]:
    rows, _ = await adb.cypher_query(
        "MATCH (u:User {org_uid: $org}) RETURN u ORDER BY u.created_at",
        {"org": org_uid},
    )
    return [User.inflate(row[0]) for row in rows]


# ── Current user (account) ──────────────────────────────────────────────────


@router.get("/me/profile", response_model=MeDTO, operation_id="opensweep_me_profile")
async def me_profile(user: UserDTO = Depends(get_current_user)) -> MeDTO:
    """Everything the shell needs: identity, org, pending invitations."""
    org = await Organization.nodes.get_or_none(uid=user.org_uid)
    org_dto = (
        await _org_dto(org, user)
        if org is not None
        else OrganizationDTO(uid=user.org_uid, name=user.org_uid, is_owner=user.org_role == "owner")
    )
    pending: list[MyInvitationDTO] = []
    for inv in await pending_invitations_for_email(user.email):
        if inv.org_uid == user.org_uid:
            continue  # already a member — stale invite
        inv_org = await Organization.nodes.get_or_none(uid=inv.org_uid)
        if inv_org is None:
            continue
        pending.append(
            MyInvitationDTO(
                uid=inv.uid,
                org_uid=inv.org_uid,
                org_name=inv_org.name,
                role=inv.role,
                created_at=inv.created_at,
            )
        )
    return MeDTO(
        uid=user.uid,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        org_role=user.org_role,
        is_platform_admin=user.is_platform_admin,
        onboarded=user.onboarded,
        org=org_dto,
        pending_invitations=pending,
    )


@router.patch("/me", response_model=UserDTO, operation_id="opensweep_update_me")
async def update_me(
    req: UpdateMeRequest, user: UserDTO = Depends(get_current_user)
) -> UserDTO:
    node = await User.nodes.get_or_none(uid=user.uid)
    if node is None:
        raise HTTPException(
            status_code=409,
            detail="account editing is unavailable in no-auth/shared-token mode",
        )
    if req.display_name is not None:
        node.display_name = req.display_name.strip()
    if req.onboarded is not None:
        node.onboarded = req.onboarded
    await node.save()
    invalidate_user_cache(user.uid)
    return user.model_copy(
        update={"display_name": node.display_name, "onboarded": bool(node.onboarded)}
    )


@router.post(
    "/me/invitations/{uid}/accept",
    response_model=UserDTO,
    operation_id="opensweep_accept_invitation",
)
async def accept_my_invitation(
    uid: str, user: UserDTO = Depends(get_current_user)
) -> UserDTO:
    """Move the current user into the inviting org. Their previous org is
    deleted if it ends up with no members and no repositories."""
    node = await User.nodes.get_or_none(uid=user.uid)
    if node is None:
        raise HTTPException(status_code=409, detail="unavailable in no-auth mode")
    inv = await OrgInvitation.nodes.get_or_none(uid=uid)
    if (
        inv is None
        or inv.status != "pending"
        or inv.email != (user.email or "").strip().lower()
    ):
        raise HTTPException(status_code=404, detail="not found")
    if inv.org_uid == user.org_uid:
        raise HTTPException(status_code=409, detail="already a member of this organization")
    if user.org_role == "owner" and await org_owner_count(user.org_uid) == 1:
        members, _ = await adb.cypher_query(
            "MATCH (u:User {org_uid: $org}) RETURN count(u)", {"org": user.org_uid}
        )
        if members and int(members[0][0]) > 1:
            raise HTTPException(
                status_code=409,
                detail="you are the only owner of your current organization — "
                "promote another owner first",
            )
    if await Organization.nodes.get_or_none(uid=inv.org_uid) is None:
        raise HTTPException(status_code=404, detail="not found")
    await accept_invitation(node, inv)
    invalidate_user_cache(user.uid)
    await write_audit(
        kind="org.member_joined",
        subject_uid=inv.org_uid,
        subject_type="Organization",
        actor_uid=user.uid,
        payload={"invitation_uid": inv.uid, "email": inv.email},
    )
    return user.model_copy(
        update={"org_uid": inv.org_uid, "role": inv.role, "org_role": "member"}
    )


# ── Organization ─────────────────────────────────────────────────────────────


@router.get("/org", response_model=OrganizationDTO, operation_id="opensweep_get_org")
async def get_org(user: UserDTO = Depends(get_current_user)) -> OrganizationDTO:
    return await _org_dto(await _get_org(user.org_uid), user)


@router.patch("/org", response_model=OrganizationDTO, operation_id="opensweep_update_org")
async def update_org(
    req: UpdateOrganizationRequest, user: UserDTO = Depends(require_org_owner)
) -> OrganizationDTO:
    org = await _get_org(user.org_uid)
    changed: list[str] = []
    if req.name is not None:
        org.name = req.name.strip()
        changed.append("name")
    if req.settings is not None:
        org.settings_json = req.settings.model_dump_json()
        changed.append("settings")
    if not changed:
        raise HTTPException(status_code=422, detail="nothing to update")
    await org.save()
    await write_audit(
        kind="org.updated",
        subject_uid=org.uid,
        subject_type="Organization",
        actor_uid=user.uid,
        payload={"fields": changed, "name": org.name},
    )
    return await _org_dto(org, user)


@router.get(
    "/org/members", response_model=list[OrgMemberDTO], operation_id="opensweep_list_org_members"
)
async def list_members(user: UserDTO = Depends(get_current_user)) -> list[OrgMemberDTO]:
    members = await _org_members(user.org_uid)
    if not members:
        # No-auth/shared-token mode has no User nodes — surface the caller.
        return [
            OrgMemberDTO(
                uid=user.uid,
                email=user.email,
                display_name=user.display_name,
                role=user.role,
                org_role=user.org_role,
                created_at=user.created_at,
            )
        ]
    return [_member_dto(m) for m in members]


@router.patch(
    "/org/members/{uid}", response_model=OrgMemberDTO, operation_id="opensweep_update_org_member"
)
async def update_member(
    uid: str, req: UpdateMemberRequest, user: UserDTO = Depends(require_org_owner)
) -> OrgMemberDTO:
    member = await User.nodes.get_or_none(uid=uid)
    if member is None or member.org_uid != user.org_uid:
        raise HTTPException(status_code=404, detail="not found")
    if req.role is not None:
        if req.role not in USER_ROLES:
            raise HTTPException(status_code=422, detail=f"role must be one of {sorted(USER_ROLES)}")
        member.role = req.role
    if req.org_role is not None:
        if req.org_role not in ORG_ROLES:
            raise HTTPException(
                status_code=422, detail=f"org_role must be one of {sorted(ORG_ROLES)}"
            )
        if (
            member.org_role == "owner"
            and req.org_role != "owner"
            and await org_owner_count(user.org_uid) == 1
        ):
            raise HTTPException(
                status_code=409, detail="an organization must keep at least one owner"
            )
        member.org_role = req.org_role
        if req.org_role == "owner":
            member.role = "admin"  # owners manage the org — they get full capability
    await member.save()
    invalidate_user_cache(member.uid)
    await write_audit(
        kind="org.member_updated",
        subject_uid=member.uid,
        subject_type="User",
        actor_uid=user.uid,
        payload={"role": member.role, "org_role": member.org_role},
    )
    return _member_dto(member)


@router.delete("/org/members/{uid}", operation_id="opensweep_remove_org_member")
async def remove_member(uid: str, user: UserDTO = Depends(require_org_owner)) -> dict:
    member = await User.nodes.get_or_none(uid=uid)
    if member is None or member.org_uid != user.org_uid:
        raise HTTPException(status_code=404, detail="not found")
    if member.org_role == "owner" and await org_owner_count(user.org_uid) == 1:
        raise HTTPException(
            status_code=409, detail="an organization must keep at least one owner"
        )
    # The removed user keeps a working account: fresh personal org, owner.
    org = await create_personal_org(
        creator_uid=member.uid, display_name=member.display_name, email=member.email
    )
    await move_user_to_org(member, org.uid, role="admin", org_role="owner")
    invalidate_user_cache(member.uid)
    await write_audit(
        kind="org.member_removed",
        subject_uid=user.org_uid,
        subject_type="Organization",
        actor_uid=user.uid,
        payload={"member_uid": member.uid, "email": member.email},
    )
    return {"ok": True}


# ── Invitations ──────────────────────────────────────────────────────────────


@router.get(
    "/org/invitations",
    response_model=list[OrgInvitationDTO],
    operation_id="opensweep_list_org_invitations",
)
async def list_invitations(
    user: UserDTO = Depends(require_org_owner),
) -> list[OrgInvitationDTO]:
    rows, _ = await adb.cypher_query(
        "MATCH (i:OrgInvitation {org_uid: $org, status: 'pending'}) "
        "RETURN i ORDER BY i.created_at DESC",
        {"org": user.org_uid},
    )
    return [_invitation_dto(OrgInvitation.inflate(row[0])) for row in rows]


@router.post(
    "/org/invitations",
    response_model=OrgInvitationDTO,
    status_code=201,
    operation_id="opensweep_create_org_invitation",
)
async def create_invitation(
    req: CreateInvitationRequest, user: UserDTO = Depends(require_org_owner)
) -> OrgInvitationDTO:
    if req.role not in USER_ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(USER_ROLES)}")
    rows, _ = await adb.cypher_query(
        "MATCH (u:User {org_uid: $org}) WHERE toLower(u.email) = $email RETURN 1 LIMIT 1",
        {"org": user.org_uid, "email": req.email},
    )
    if rows:
        raise HTTPException(status_code=409, detail=f"{req.email} is already a member")
    rows, _ = await adb.cypher_query(
        "MATCH (i:OrgInvitation {org_uid: $org, email: $email, status: 'pending'}) "
        "RETURN 1 LIMIT 1",
        {"org": user.org_uid, "email": req.email},
    )
    if rows:
        raise HTTPException(status_code=409, detail=f"{req.email} already has a pending invitation")
    inv = await OrgInvitation(
        org_uid=user.org_uid, email=req.email, role=req.role, invited_by=user.uid
    ).save()
    await write_audit(
        kind="org.invitation_created",
        subject_uid=user.org_uid,
        subject_type="Organization",
        actor_uid=user.uid,
        payload={"email": req.email, "role": req.role},
    )
    return _invitation_dto(inv)


@router.delete("/org/invitations/{uid}", operation_id="opensweep_revoke_org_invitation")
async def revoke_invitation(uid: str, user: UserDTO = Depends(require_org_owner)) -> dict:
    inv = await OrgInvitation.nodes.get_or_none(uid=uid)
    if inv is None or inv.org_uid != user.org_uid:
        raise HTTPException(status_code=404, detail="not found")
    if inv.status == "pending":
        inv.status = "revoked"
        await inv.save()
        await write_audit(
            kind="org.invitation_revoked",
            subject_uid=user.org_uid,
            subject_type="Organization",
            actor_uid=user.uid,
            payload={"email": inv.email},
        )
    return {"ok": True}
