"""Repository audit coverage — the per-scope latest Checked stamp
(KNOWLEDGE_V3_CHECKED.md §4).

Coverage history only: when/at-what-revision/with-what-outcome each doc
scope was last audited. Staleness (needs-review) is the single derived
review axis and comes from the Doc DTO's `stale` field, not from here.
"""

from typing import Any

from fastapi import APIRouter, Depends

from api.dependencies import get_current_user
from domains.checked.services import checked_service
from domains.tenancy import require_repo_in_org
from domains.users.schemas import UserDTO

router = APIRouter(prefix="/api/v1/repositories", tags=["freshness"])


@router.get("/{repository_uid}/freshness", operation_id="opensweep_repository_freshness")
async def repository_freshness(
    repository_uid: str,
    user: UserDTO = Depends(get_current_user),
) -> list[dict[str, Any]]:
    await require_repo_in_org(repository_uid, user.org_uid)
    return await checked_service.audit_coverage(repository_uid=repository_uid)
