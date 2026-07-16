"""User node — hardcoded local user, or Zitadel-resolved when OIDC is on."""

from neomodel import (
    AsyncStructuredNode,
    BooleanProperty,
    DateTimeProperty,
    StringProperty,
)


class User(AsyncStructuredNode):
    # Zitadel `sub` for OIDC users; LOCAL_USER_UID for the no-auth local user.
    uid = StringProperty(unique_index=True, required=True)
    email = StringProperty(required=True)
    display_name = StringProperty(required=True)
    # Capability role WITHIN the org: viewer < maintainer < admin
    # (PLATFORM_V2_DESIGN.md §3). OpenSweep-managed — set at provisioning (org
    # creators get admin, invitees get the invitation's role) and editable by
    # org owners. Gate-1 requires maintainer+.
    role = StringProperty(default="admin")
    # OpenSweep org membership — the tenancy root. Every user belongs to exactly
    # one org; provisioning guarantees it's populated (personal org on first
    # login, invitation target, or migration from idp_org_id).
    org_uid = StringProperty(default="", index=True)
    # owner | member — owners manage the org (rename, members, invitations).
    org_role = StringProperty(default="member")
    # Cleared for brand-new org creators so the frontend runs the welcome
    # flow once; invitees and migrated users skip it.
    onboarded = BooleanProperty(default=True)
    # Zitadel organization id (`urn:zitadel:iam:user:resourceowner:id`) —
    # informational only since OpenSweep took over org membership; kept because
    # pre-membership deployments used it as the org uid (migration seam).
    idp_org_id = StringProperty(default="")
    created_at = DateTimeProperty(default_now=True)


USER_ROLES = {"viewer", "maintainer", "admin"}
