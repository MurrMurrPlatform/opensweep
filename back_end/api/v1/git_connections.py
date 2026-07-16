"""Org PAT git connections — the self-serve OSS connect path.

An org maintainer pastes a (fine-grained) GitHub token; it becomes a sealed
GitConnection(kind="pat") whose repos show up in the connect dialog next to
GitHub App installations (api/v1/github_app.py). The token itself is never
returned by any endpoint.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import require_role
from domains.organizations.services.git_connections import (
    PatValidationError,
    connection_summary,
    create_pat_connection,
    delete_pat_connection,
    org_pat_connections,
)
from domains.users.schemas import UserDTO

router = APIRouter(prefix="/api/v1/git/connections", tags=["git-connections"])


class PatConnectionInfo(BaseModel):
    uid: str
    kind: str = "pat"
    account: str = ""
    created_at: str = ""


class ConnectionsResponse(BaseModel):
    connections: list[PatConnectionInfo] = []


class AddPatRequest(BaseModel):
    token: str


@router.get("", response_model=ConnectionsResponse, operation_id="opensweep_git_connections")
async def list_connections(
    user: UserDTO = Depends(require_role("maintainer")),
) -> ConnectionsResponse:
    rows = await org_pat_connections(user.org_uid)
    return ConnectionsResponse(
        connections=[PatConnectionInfo(**connection_summary(c)) for c in rows]
    )


@router.post(
    "",
    response_model=PatConnectionInfo,
    status_code=201,
    operation_id="opensweep_git_connections_add",
)
async def add_pat_connection(
    req: AddPatRequest,
    user: UserDTO = Depends(require_role("maintainer")),
) -> PatConnectionInfo:
    """Validate the token against GitHub and connect it to the caller's org.
    Idempotent for a token this org already connected (200-shaped 201)."""
    try:
        conn = await create_pat_connection(
            org_uid=user.org_uid, token=req.token, linked_by=user.uid
        )
    except PatValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"could not reach GitHub to validate the token: {exc}"
        ) from exc
    return PatConnectionInfo(**connection_summary(conn))


@router.delete("/{uid}", operation_id="opensweep_git_connections_remove")
async def remove_pat_connection(
    uid: str,
    user: UserDTO = Depends(require_role("maintainer")),
) -> dict:
    """Forget one of the org's PAT connections. Repos registered through it
    stay registered and fall back to the env PAT (or fail visibly)."""
    removed = await delete_pat_connection(uid, user.org_uid, actor_uid=user.uid)
    if not removed:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}
