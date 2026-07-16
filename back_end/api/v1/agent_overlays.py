"""Org agent overlay routes — per-org tuning of each playbook's task
instructions (spec: docs/superpowers/specs/2026-07-14-org-agent-overlays-design.md).

Tenancy: org resolved from the current user (same pattern as org-scoped LLM
providers); an overlay is only visible to / editable by its owning org.
Permissions: ANY org member may write (spec decision 5) — attribution,
revision history, and audit events are the guardrails.
"""

from fastapi import APIRouter, Depends, Response

from api.dependencies import get_current_user
from domains.agent_overlays.schemas import (
    OverlayDTO,
    OverlayRevisionDTO,
    PlaybookOverlayStatusDTO,
    PreviewOverlayRequest,
    PreviewOverlayResponse,
    RevertOverlayRequest,
    UpsertOverlayRequest,
)
from domains.agent_overlays.services import overlay_service
from domains.agent_overlays.services.composition import preview_composed_prompt
from domains.users.schemas import UserDTO

router = APIRouter(prefix="/api/v1/agent-overlays", tags=["agent-overlays"])


@router.get("", response_model=list[PlaybookOverlayStatusDTO])
async def list_agent_overlays(user: UserDTO = Depends(get_current_user)):
    """Every playbook with its platform base preview + this org's overlay."""
    overlay_service.require_org(user.org_uid)
    return await overlay_service.list_playbook_statuses(user.org_uid)


@router.put("/{playbook}", response_model=OverlayDTO)
async def upsert_agent_overlay(
    playbook: str,
    req: UpsertOverlayRequest,
    user: UserDTO = Depends(get_current_user),
):
    node = await overlay_service.upsert_overlay(
        org_uid=user.org_uid,
        playbook=playbook,
        mode=req.mode,
        body=req.body,
        enabled=req.enabled,
        actor_uid=user.uid,
    )
    return overlay_service.overlay_to_dto(node)


@router.delete("/{playbook}", status_code=204)
async def delete_agent_overlay(
    playbook: str, user: UserDTO = Depends(get_current_user)
):
    """Restore the platform default (removes the overlay; history is kept)."""
    await overlay_service.delete_overlay(
        org_uid=user.org_uid, playbook=playbook, actor_uid=user.uid
    )
    return Response(status_code=204)


@router.get("/{playbook}/revisions", response_model=list[OverlayRevisionDTO])
async def list_agent_overlay_revisions(
    playbook: str, user: UserDTO = Depends(get_current_user)
):
    return await overlay_service.list_revisions(user.org_uid, playbook)


@router.post("/{playbook}/revert", response_model=OverlayDTO)
async def revert_agent_overlay(
    playbook: str,
    req: RevertOverlayRequest,
    user: UserDTO = Depends(get_current_user),
):
    """Create a NEW head revision copying revision `rev` (append-only)."""
    node = await overlay_service.revert_overlay(
        org_uid=user.org_uid, playbook=playbook, rev=req.rev, actor_uid=user.uid
    )
    return overlay_service.overlay_to_dto(node)


@router.post("/{playbook}/preview", response_model=PreviewOverlayResponse)
async def preview_agent_overlay(
    playbook: str,
    req: PreviewOverlayRequest,
    user: UserDTO = Depends(get_current_user),
):
    """Compose the full prompt for a DRAFT overlay — nothing is persisted."""
    org = overlay_service.require_org(user.org_uid)
    pb = overlay_service.validate_playbook(playbook)
    mode, body = overlay_service.validate_mode_and_body(req.mode, req.body)
    prompt = await preview_composed_prompt(org_uid=org, playbook=pb, mode=mode, body=body)
    return PreviewOverlayResponse(playbook=pb, mode=mode, prompt=prompt)
