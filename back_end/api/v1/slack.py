"""Slack integration routes — per-org OAuth v2 install, notification rules,
and the inbound Events API / slash-command surface.

Auth model:
  - status / channels / rules reads   → any org member
  - install / disconnect / rule CRUD  → org admins (capability role)
  - /oauth/callback                   → browser redirect from Slack; trust =
    the signed, single-use install state (org-bound), TokenAuthMiddleware-exempt
  - /events + /commands               → Slack servers; trust = the v0 request
    signature (SLACK_SIGNING_SECRET), TokenAuthMiddleware-exempt

Inbound conversation work (workspace clone + LLM turns) always leaves the
request via asyncio.create_task — Slack requires an ack within 3 seconds.
"""

from __future__ import annotations

import asyncio
import json
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from api.dependencies import get_current_user, require_role
from api.v1.github_app import consume_state, remember_state
from config import settings
from domains.slack import inbound
from domains.slack import service as slack_service
from domains.slack.client import SlackApiError, oauth_access, post_message, revoke_token
from domains.slack.events import CATALOG
from domains.slack.formatting import format_event_message
from domains.slack.schemas import (
    CreateSlackRuleRequest,
    SlackChannelDTO,
    SlackEventTypeDTO,
    SlackInstallUrlDTO,
    SlackRuleDTO,
    SlackStatusDTO,
    UpdateSlackRuleRequest,
)
from domains.slack.signing import (
    STATE_MAX_AGE_SECONDS,
    mint_install_state,
    verify_install_state,
    verify_slack_signature,
)
from domains.users.schemas import UserDTO
from logging_config import logger

router = APIRouter(prefix="/api/v1/slack", tags=["slack"])

_EVENT_CATALOG_DTO = [
    SlackEventTypeDTO(event_type=e.event_type, label=e.label, description=e.description)
    for e in CATALOG
]


def _frontend_settings_url(result: str) -> str:
    base = (settings.OPENSWEEP_FRONTEND_BASE_URL or "").rstrip("/")
    return f"{base}/settings/slack?slack={result}"


# ── Status / install / disconnect ────────────────────────────────────────────


@router.get("/status", response_model=SlackStatusDTO, operation_id="opensweep_slack_status")
async def slack_status(user: UserDTO = Depends(get_current_user)) -> SlackStatusDTO:
    connection = await slack_service.get_connection(user.org_uid)
    return SlackStatusDTO(
        configured=slack_service.slack_app_configured(),
        connected=connection is not None,
        team_id=connection.team_id if connection else "",
        team_name=(connection.team_name or "") if connection else "",
        bot_user_id=(connection.bot_user_id or "") if connection else "",
        scopes=[s for s in ((connection.scopes or "").split(",") if connection else []) if s],
        installed_by=(connection.installed_by or "") if connection else "",
        event_types=_EVENT_CATALOG_DTO,
    )


@router.get("/install", response_model=SlackInstallUrlDTO, operation_id="opensweep_slack_install")
async def slack_install_url(user: UserDTO = Depends(require_role("admin"))) -> SlackInstallUrlDTO:
    if not slack_service.slack_app_configured():
        raise HTTPException(
            status_code=409,
            detail="Slack app is not configured on this deployment "
            "(SLACK_CLIENT_ID / SLACK_CLIENT_SECRET / SLACK_SIGNING_SECRET)",
        )
    state = mint_install_state(user.org_uid, user.uid)
    await remember_state(state, ttl_seconds=STATE_MAX_AGE_SECONDS)
    return SlackInstallUrlDTO(url=slack_service.build_authorize_url(state))


@router.get("/oauth/callback", operation_id="opensweep_slack_oauth_callback")
async def slack_oauth_callback(
    code: str = "", state: str = "", error: str = ""
) -> RedirectResponse:
    """Slack redirects the installing admin's browser here. No OpenSweep token —
    trust is the signed, single-use install state minted by /install."""
    if error:
        # The admin denied the install (or Slack errored) — never a 4xx page.
        return RedirectResponse(url=_frontend_settings_url("denied"), status_code=302)
    org_uid, installer_uid = verify_install_state(state)
    if not org_uid:
        raise HTTPException(status_code=403, detail="invalid or expired state")
    if not code:
        # Check BEFORE consuming: a code-less redirect must not burn the
        # single-use state — the admin's retry should still work.
        raise HTTPException(status_code=400, detail="missing code")
    if not await consume_state(state):
        raise HTTPException(status_code=403, detail="state already used")
    try:
        payload = await oauth_access(code, slack_service.oauth_redirect_uri())
    except SlackApiError as exc:
        logger.warning(f"Slack OAuth exchange failed: {exc.error}", extra={"tag": "slack"})
        return RedirectResponse(url=_frontend_settings_url("error"), status_code=302)
    try:
        await slack_service.store_connection(org_uid, payload, installed_by=installer_uid)
    except HTTPException as exc:
        # This is a browser navigation — land on the settings page with a
        # readable outcome, never a raw JSON error. The freshly issued token
        # is discarded, so revoke it (best-effort).
        logger.warning(f"Slack connection not stored: {exc.detail}", extra={"tag": "slack"})
        await revoke_token(str(payload.get("access_token") or ""))
        result = "conflict" if exc.status_code == 409 else "error"
        return RedirectResponse(url=_frontend_settings_url(result), status_code=302)
    return RedirectResponse(url=_frontend_settings_url("connected"), status_code=302)


@router.delete("/connection", operation_id="opensweep_slack_disconnect")
async def slack_disconnect(user: UserDTO = Depends(require_role("admin"))) -> dict:
    removed = await slack_service.delete_connection(user.org_uid, actor_uid=user.uid)
    if not removed:
        raise HTTPException(status_code=404, detail="Slack is not connected")
    return {"disconnected": True}


# ── Channels + rules ─────────────────────────────────────────────────────────


@router.get("/channels", response_model=list[SlackChannelDTO], operation_id="opensweep_slack_channels")
async def slack_channels(user: UserDTO = Depends(get_current_user)) -> list[SlackChannelDTO]:
    connection = await slack_service.get_connection(user.org_uid)
    if connection is None:
        raise HTTPException(status_code=404, detail="Slack is not connected")
    try:
        return await slack_service.list_channels(connection)
    except SlackApiError as exc:
        raise HTTPException(status_code=502, detail=f"Slack API error: {exc.error}") from exc


@router.get("/rules", response_model=list[SlackRuleDTO], operation_id="opensweep_slack_list_rules")
async def slack_list_rules(user: UserDTO = Depends(get_current_user)) -> list[SlackRuleDTO]:
    rules = await slack_service.list_rules(user.org_uid)
    return [slack_service.rule_to_dto(r) for r in rules]


@router.post("/rules", response_model=SlackRuleDTO, operation_id="opensweep_slack_create_rule")
async def slack_create_rule(
    req: CreateSlackRuleRequest, user: UserDTO = Depends(require_role("admin"))
) -> SlackRuleDTO:
    rule = await slack_service.create_rule(user.org_uid, req, created_by=user.uid)
    return slack_service.rule_to_dto(rule)


@router.patch(
    "/rules/{rule_uid}", response_model=SlackRuleDTO, operation_id="opensweep_slack_update_rule"
)
async def slack_update_rule(
    rule_uid: str, req: UpdateSlackRuleRequest, user: UserDTO = Depends(require_role("admin"))
) -> SlackRuleDTO:
    rule = await slack_service.update_rule(user.org_uid, rule_uid, req, actor_uid=user.uid)
    return slack_service.rule_to_dto(rule)


@router.delete("/rules/{rule_uid}", operation_id="opensweep_slack_delete_rule")
async def slack_delete_rule(
    rule_uid: str, user: UserDTO = Depends(require_role("admin"))
) -> dict:
    await slack_service.delete_rule(user.org_uid, rule_uid, actor_uid=user.uid)
    return {"deleted": True}


@router.post("/rules/{rule_uid}/test", operation_id="opensweep_slack_test_rule")
async def slack_test_rule(
    rule_uid: str, user: UserDTO = Depends(require_role("admin"))
) -> dict:
    """Post a sample message through a rule so channel wiring can be checked
    without waiting for a real event."""
    connection = await slack_service.get_connection(user.org_uid)
    if connection is None:
        raise HTTPException(status_code=404, detail="Slack is not connected")
    rule = await slack_service.get_rule(user.org_uid, rule_uid)
    text, blocks = format_event_message(
        rule.event_type,
        {"payload": {}, "actor_uid": user.uid, "subject_type": "", "subject_uid": ""},
        repo_slug="",
        subject_title="Test notification from OpenSweep",
    )
    try:
        await post_message(
            slack_service.bot_token(connection),
            channel=rule.channel_id,
            text=text,
            blocks=blocks,
        )
    except SlackApiError as exc:
        raise HTTPException(status_code=502, detail=f"Slack API error: {exc.error}") from exc
    return {"sent": True}


# ── Inbound: Events API + slash commands (Slack-signed, auth-exempt) ─────────


def _verified_body(request: Request, body: bytes) -> None:
    ok = verify_slack_signature(
        signing_secret=settings.SLACK_SIGNING_SECRET,
        timestamp=request.headers.get("x-slack-request-timestamp"),
        signature=request.headers.get("x-slack-signature"),
        body=body,
    )
    if not ok:
        # Operators need this in the logs: an unset secret or clock skew
        # presents to Slack users as the bot simply ignoring everyone.
        reason = (
            "SLACK_SIGNING_SECRET is not configured"
            if not settings.SLACK_SIGNING_SECRET
            else "bad signature or timestamp outside the 5-minute window"
        )
        logger.warning(
            f"Slack request rejected on {request.url.path}: {reason}",
            extra={"tag": "slack"},
        )
        raise HTTPException(status_code=403, detail="invalid Slack signature")


@router.post("/events", operation_id="opensweep_slack_events")
async def slack_events(request: Request):
    body = await request.body()
    _verified_body(request, body)
    try:
        envelope = json.loads(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid JSON") from exc

    if envelope.get("type") == "url_verification":
        return JSONResponse({"challenge": envelope.get("challenge", "")})
    if envelope.get("type") != "event_callback":
        return JSONResponse({"ok": True})

    event = envelope.get("event") or {}
    event_type = event.get("type")
    team_id = str(envelope.get("team_id") or "")

    # Only conversational events; ignore our own/bot messages and message
    # edits (subtype) so the bot never talks to itself.
    is_dm = event_type == "message" and event.get("channel_type") == "im"
    if event_type != "app_mention" and not is_dm:
        return JSONResponse({"ok": True})
    if event.get("bot_id") or event.get("subtype"):
        return JSONResponse({"ok": True})

    connection = await slack_service.connection_for_team(team_id)
    if connection is None:
        return JSONResponse({"ok": True})
    if event.get("user") and event.get("user") == connection.bot_user_id:
        return JSONResponse({"ok": True})
    if await inbound.already_processed(str(envelope.get("event_id") or "")):
        return JSONResponse({"ok": True})

    channel = str(event.get("channel") or "")
    if is_dm:
        # A DM is one rolling conversation per channel: replies stay flat
        # (no thread anchor) and every message tries to continue the mapped
        # run first — a fresh workspace clone per DM message would be brutal.
        thread_ts = str(event.get("thread_ts") or "")
        conversation_key = thread_ts or f"dm:{channel}"
        is_new_thread = False
    else:
        thread_ts = str(event.get("thread_ts") or event.get("ts") or "")
        conversation_key = thread_ts
        is_new_thread = event.get("thread_ts") is None

    _spawn_background(
        inbound.handle_conversation(
            connection=connection,
            channel=channel,
            thread_ts=thread_ts,
            slack_user=str(event.get("user") or ""),
            text=str(event.get("text") or ""),
            is_new_thread=is_new_thread,
            conversation_key=conversation_key,
        )
    )
    return JSONResponse({"ok": True})


@router.post("/commands", operation_id="opensweep_slack_commands")
async def slack_commands(request: Request):
    body = await request.body()
    _verified_body(request, body)
    form = {k: v[0] for k, v in parse_qs(body.decode("utf-8", "replace")).items()}

    connection = await slack_service.connection_for_team(str(form.get("team_id") or ""))
    if connection is None:
        return JSONResponse(
            {"response_type": "ephemeral", "text": "This Slack workspace is not connected to OpenSweep."}
        )

    sub, rest = inbound.parse_command(str(form.get("text") or ""))
    if sub == "help":
        return JSONResponse({"response_type": "ephemeral", "text": inbound.HELP_TEXT})
    if sub == "repos":
        text = await inbound.command_repos_reply(connection.org_uid)
        return JSONResponse({"response_type": "ephemeral", "text": text})
    if sub == "runs":
        text = await inbound.command_runs_reply(connection.org_uid)
        return JSONResponse({"response_type": "ephemeral", "text": text})

    # ask — long-running: ack now, answer lands in the channel as a thread.
    _spawn_background(
        inbound.handle_conversation(
            connection=connection,
            channel=str(form.get("channel_id") or ""),
            thread_ts="",
            slack_user=str(form.get("user_id") or ""),
            text=rest,
            is_new_thread=True,
        )
    )
    return JSONResponse(
        {
            "response_type": "ephemeral",
            "text": ":hourglass_flowing_sand: Working on it — I'll answer in this "
            "channel. (If nothing appears, invite me: `/invite @OpenSweep`.)",
        }
    )


# Strong references keep fire-and-forget conversations alive: the event loop
# holds tasks only weakly, so an unreferenced task can be garbage-collected
# mid-flight — the user would get the "working on it" ack and then silence.
_background_tasks: set[asyncio.Task] = set()


def _spawn_background(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)

    def _done(done: asyncio.Task) -> None:
        _background_tasks.discard(done)
        try:
            done.result()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"Slack background task crashed: {type(exc).__name__}: {exc}",
                extra={"tag": "slack"},
            )

    task.add_done_callback(_done)
