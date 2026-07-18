"""Authenticated consent endpoint for the `opensweep connect` OAuth gateway.

The SPA consent view (/connect/authorize) calls this as the logged-in user
(Zitadel OIDC bearer). Approval re-validates everything against the DB —
the browser-carried params are untrusted — checks the org's connect
entitlement, mints the single-use authorization code, and returns the final
client redirect for the SPA to follow.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_current_user
from domains.oauth_mcp.services import oauth_service
from domains.oauth_mcp.services.entitlements import can_use_connect
from domains.users.schemas import UserDTO
from infrastructure.audit import write_audit

router = APIRouter(prefix="/api/v1/oauth-mcp", tags=["oauth-mcp"])


class ApproveRequest(BaseModel):
    client_id: str = Field(min_length=1)
    redirect_uri: str = Field(min_length=1)
    state: str = ""
    code_challenge: str = Field(min_length=1)
    scope: str = "mcp:read"


@router.post("/approve", operation_id="opensweep_oauth_mcp_approve")
async def approve(req: ApproveRequest, user: UserDTO = Depends(get_current_user)) -> dict:
    if not await can_use_connect(user.org_uid):
        raise HTTPException(
            status_code=403, detail="connecting local agents is not enabled for this organization"
        )
    client = await oauth_service.get_client(req.client_id)
    if not oauth_service.redirect_uri_allowed(req.redirect_uri, client.redirect_uris or []):
        raise HTTPException(status_code=400, detail="invalid_redirect_uri")
    scope = oauth_service.normalize_scope(req.scope)
    code = await oauth_service.issue_code(
        client=client,
        user_uid=user.uid,
        scope=scope,
        code_challenge=req.code_challenge,
        redirect_uri=req.redirect_uri,
    )
    await write_audit(
        kind="oauth_mcp.consent_granted",
        subject_uid=client.uid,
        subject_type="OAuthClient",
        actor_uid=user.uid,
        payload={"scope": scope, "client_name": client.name},
    )
    from urllib.parse import urlencode

    params = {"code": code}
    if req.state:
        params["state"] = req.state
    sep = "&" if "?" in req.redirect_uri else "?"
    return {"redirect_to": f"{req.redirect_uri}{sep}{urlencode(params)}"}
