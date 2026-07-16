"""The hardcoded local user (no-auth and shared-token modes).

Lives in the fixed LOCAL_ORG_UID org — single-tenant operation is just
multi-tenancy with one org, so the tenancy checks stay uniform.
"""

from datetime import UTC, datetime

from config import settings
from domains.organizations.models import LOCAL_ORG_UID
from domains.users.schemas import UserDTO

LOCAL_USER_UID = "local-user"


def get_local_user() -> UserDTO:
    return UserDTO(
        uid=LOCAL_USER_UID,
        email=settings.OPENSWEEP_LOCAL_USER_EMAIL,
        display_name=settings.OPENSWEEP_LOCAL_USER_DISPLAY_NAME,
        role="admin",
        org_uid=LOCAL_ORG_UID,
        org_role="owner",
        is_platform_admin=True,  # no-auth/shared-token caller IS the operator
        onboarded=True,
        created_at=datetime.now(UTC),
    )
