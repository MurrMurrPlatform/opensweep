"""Agent prompts library — CRUD + ECC import."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_current_user, require_platform_admin
from domains.agents.schemas import (
    AgentPromptDTO,
    CreateAgentPromptRequest,
    ImportEccResult,
    UpdateAgentPromptRequest,
)
from domains.agents.services.agent_prompt_service import (
    create_prompt,
    delete_prompt,
    get_prompt,
    list_prompts,
    update_prompt,
)
from domains.agents.services.ecc_import import import_ecc
from domains.users.schemas import UserDTO
from infrastructure.audit import write_audit

router = APIRouter(prefix="/api/v1/agent-prompts", tags=["agent_prompts"])


@router.get("", response_model=list[AgentPromptDTO])
async def list_agent_prompts(
    tag: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    enabled_only: bool = Query(False),
    user: UserDTO = Depends(get_current_user),
):
    return await list_prompts(tag=tag, source=source, enabled_only=enabled_only)


@router.get("/{uid}", response_model=AgentPromptDTO)
async def get_agent_prompt(uid: str, user: UserDTO = Depends(get_current_user)):
    return await get_prompt(uid)


@router.post("", response_model=AgentPromptDTO, status_code=201)
async def create_agent_prompt(
    req: CreateAgentPromptRequest,
    user: UserDTO = Depends(require_platform_admin),
):
    dto = await create_prompt(req, source="user")
    await write_audit(
        kind="agent_prompt.created",
        subject_uid=dto.uid,
        subject_type="AgentPrompt",
        actor_uid=user.uid,
        payload={"title": dto.title, "source": "user"},
    )
    return dto


@router.patch("/{uid}", response_model=AgentPromptDTO)
async def update_agent_prompt(
    uid: str,
    req: UpdateAgentPromptRequest,
    user: UserDTO = Depends(require_platform_admin),
):
    dto = await update_prompt(uid, req)
    await write_audit(
        kind="agent_prompt.updated",
        subject_uid=uid,
        subject_type="AgentPrompt",
        actor_uid=user.uid,
        payload={"changed": list(req.model_dump(exclude_unset=True).keys())},
    )
    return dto


@router.delete("/{uid}", status_code=204)
async def delete_agent_prompt(uid: str, user: UserDTO = Depends(require_platform_admin)):
    await delete_prompt(uid)
    await write_audit(
        kind="agent_prompt.deleted",
        subject_uid=uid,
        subject_type="AgentPrompt",
        actor_uid=user.uid,
    )


@router.post("/import-ecc", response_model=ImportEccResult)
async def import_ecc_endpoint(user: UserDTO = Depends(require_platform_admin)):
    result = await import_ecc()
    await write_audit(
        kind="agent_prompt.imported_ecc",
        subject_uid="agent-prompts",
        subject_type="AgentPrompt",
        actor_uid=user.uid,
        payload={
            "imported": result.imported,
            "skipped_user_edited": result.skipped_user_edited,
            "source_commit": result.source_commit,
            "error_count": len(result.errors),
        },
    )
    return result
