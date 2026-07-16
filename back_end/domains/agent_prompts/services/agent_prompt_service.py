"""CRUD helpers for AgentPrompt."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException

from domains.agent_prompts.models import AgentPrompt
from domains.agent_prompts.schemas import (
    AgentPromptDTO,
    CreateAgentPromptRequest,
    UpdateAgentPromptRequest,
)


def _to_dto(p: AgentPrompt) -> AgentPromptDTO:
    return AgentPromptDTO(
        uid=p.uid,
        title=p.title,
        description=p.description or "",
        body=p.body or "",
        default_job_type=p.default_job_type or "audit",
        default_scope=p.default_scope or "repository",
        default_effort=p.default_effort or "normal",
        tags=list(p.tags or []),
        source=p.source or "user",
        source_url=p.source_url or "",
        source_commit=p.source_commit or "",
        enabled=bool(p.enabled),
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


async def list_prompts(
    *,
    tag: Optional[str] = None,
    source: Optional[str] = None,
    enabled_only: bool = False,
) -> list[AgentPromptDTO]:
    rows = await AgentPrompt.nodes.all()
    out: list[AgentPromptDTO] = []
    for p in rows:
        if tag and tag not in (p.tags or []):
            continue
        if source and (p.source or "") != source:
            continue
        if enabled_only and not p.enabled:
            continue
        out.append(_to_dto(p))
    out.sort(key=lambda d: (d.source != "imported", d.title.lower()))
    return out


async def get_prompt(uid: str) -> AgentPromptDTO:
    p = await AgentPrompt.nodes.get_or_none(uid=uid)
    if p is None:
        raise HTTPException(status_code=404, detail=f"AgentPrompt {uid} not found")
    return _to_dto(p)


async def get_prompt_model(uid: str) -> Optional[AgentPrompt]:
    return await AgentPrompt.nodes.get_or_none(uid=uid)


async def create_prompt(req: CreateAgentPromptRequest, *, source: str = "user") -> AgentPromptDTO:
    p = AgentPrompt(
        uid=uuid4().hex,
        title=req.title,
        description=req.description,
        body=req.body,
        default_job_type=req.default_job_type,
        default_scope=req.default_scope,
        default_effort=req.default_effort,
        tags=list(req.tags or []),
        source=source,
        enabled=req.enabled,
    )
    await p.save()
    return _to_dto(p)


async def update_prompt(uid: str, req: UpdateAgentPromptRequest) -> AgentPromptDTO:
    p = await AgentPrompt.nodes.get_or_none(uid=uid)
    if p is None:
        raise HTTPException(status_code=404, detail=f"AgentPrompt {uid} not found")
    data = req.model_dump(exclude_unset=True)
    user_edited_fields = {"title", "description", "body", "default_scope", "default_effort", "default_job_type", "tags"}
    if any(k in data for k in user_edited_fields) and p.source == "imported":
        # Once edited, this becomes a user prompt (re-import won't clobber).
        p.source = "user"
    for key, value in data.items():
        setattr(p, key, value)
    p.updated_at = datetime.now(timezone.utc)
    await p.save()
    return _to_dto(p)


async def delete_prompt(uid: str) -> None:
    p = await AgentPrompt.nodes.get_or_none(uid=uid)
    if p is None:
        raise HTTPException(status_code=404, detail=f"AgentPrompt {uid} not found")
    await p.delete()
