"""Repository freshness — derived from Checked stamps (KNOWLEDGE_V3_CHECKED.md §4)."""

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
    return await checked_service.freshness(repository_uid=repository_uid)
