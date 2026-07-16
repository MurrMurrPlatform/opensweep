"""User DTOs + role ordering (viewer < maintainer < admin)."""

from datetime import datetime

from pydantic import BaseModel

# Ordered privilege levels — Gate-1 (ticket approval) requires maintainer+.
ROLE_ORDER = {"viewer": 0, "maintainer": 1, "admin": 2}


def role_at_least(role: str, minimum: str) -> bool:
    """True when `role` grants at least `minimum` privileges.

    Unknown roles never qualify; unknown minimums are unsatisfiable.
    """
    return ROLE_ORDER.get(role, -1) >= ROLE_ORDER.get(minimum, len(ROLE_ORDER))


class UserDTO(BaseModel):
    uid: str
    email: str
    display_name: str
    role: str = "admin"
    # Tenancy root — every authenticated user belongs to exactly one org
    # (OpenSweep-provisioned; LOCAL_ORG_UID in no-auth mode). Never empty.
    org_uid: str
    # owner | member — owners manage the org (rename, members, invitations).
    org_role: str = "member"
    # Instance operator: from the Zitadel project role `admin` (granted by the
    # bootstrap script), or always true in no-auth/shared-token mode. Gates
    # platform-level assets (LLM providers, agent prompts, run policies,
    # platform config, GitHub App credentials) — NOT tenant data.
    is_platform_admin: bool = False
    # False only for fresh org creators until they finish/skip the welcome flow.
    onboarded: bool = True
    created_at: datetime | None = None
