"""Sandbox routes — list and destroy."""

from fastapi import APIRouter, Depends

from api.dependencies import get_current_user, get_sandbox_service
from domains.execution.models import Sandbox
from domains.execution.schemas import SandboxDTO
from domains.execution.services.sandbox_service import SandboxService
from domains.tenancy import org_repo_uids, require_repo_in_org
from domains.users.schemas import UserDTO

router = APIRouter(prefix="/api/v1/sandboxes", tags=["sandboxes"])


@router.get("", response_model=list[SandboxDTO])
async def list_sandboxes(
    svc: SandboxService = Depends(get_sandbox_service),
    user: UserDTO = Depends(get_current_user),
):
    allowed = await org_repo_uids(user.org_uid)
    return [s for s in await svc.list_active() if s.repository_uid in allowed]


@router.delete("/{uid}", response_model=SandboxDTO)
async def destroy_sandbox(
    uid: str,
    svc: SandboxService = Depends(get_sandbox_service),
    user: UserDTO = Depends(get_current_user),
):
    node = await Sandbox.nodes.get_or_none(uid=uid)
    if node is not None:
        await require_repo_in_org(node.repository_uid, user.org_uid)
    return await svc.destroy(uid, actor_uid=user.uid)
