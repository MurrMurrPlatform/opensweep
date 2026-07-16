"""Thin async Slack Web API client (httpx) — the only module that talks to
slack.com. Every call raises SlackApiError on transport failure or an
`ok: false` API response, so callers never have to inspect Slack envelopes.
"""

from __future__ import annotations

from typing import Any

import httpx

from config import settings

SLACK_API_BASE = "https://slack.com/api"
_TIMEOUT = 15.0


class SlackApiError(RuntimeError):
    """A Slack Web API call failed. `error` carries Slack's error code
    ("channel_not_found", "invalid_auth", …) or "transport"."""

    def __init__(self, method: str, error: str):
        super().__init__(f"Slack API {method} failed: {error}")
        self.method = method
        self.error = error


async def slack_call(
    method: str,
    *,
    token: str | None = None,
    json_payload: dict[str, Any] | None = None,
    form: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST one Web API method. json_payload and form are mutually exclusive
    (Slack's OAuth endpoints only accept form encoding)."""
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            if form is not None:
                resp = await client.post(
                    f"{SLACK_API_BASE}/{method}", data=form, headers=headers
                )
            else:
                resp = await client.post(
                    f"{SLACK_API_BASE}/{method}",
                    json=json_payload or {},
                    headers={**headers, "Content-Type": "application/json; charset=utf-8"},
                )
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SlackApiError(method, f"transport: {exc}") from exc
    if not isinstance(data, dict) or not data.get("ok"):
        raise SlackApiError(method, str((data or {}).get("error", "unknown_error")))
    return data


async def oauth_access(code: str, redirect_uri: str) -> dict[str, Any]:
    """Exchange an OAuth v2 code for a bot token (oauth.v2.access)."""
    return await slack_call(
        "oauth.v2.access",
        form={
            "code": code,
            "client_id": settings.SLACK_CLIENT_ID,
            "client_secret": settings.SLACK_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
        },
    )


async def post_message(
    token: str,
    *,
    channel: str,
    text: str,
    blocks: list[dict[str, Any]] | None = None,
    thread_ts: str | None = None,
    unfurl_links: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "channel": channel,
        "text": text,
        "unfurl_links": unfurl_links,
        "unfurl_media": False,
    }
    if blocks:
        payload["blocks"] = blocks
    if thread_ts:
        payload["thread_ts"] = thread_ts
    return await slack_call("chat.postMessage", token=token, json_payload=payload)


async def revoke_token(token: str) -> None:
    """Best-effort auth.revoke — an already-revoked token is not an error."""
    try:
        await slack_call("auth.revoke", token=token, form={})
    except SlackApiError:
        pass


async def list_channels(token: str, *, limit: int = 1000) -> list[dict[str, Any]]:
    """Public + private channels the bot can see, paginated up to `limit`."""
    channels: list[dict[str, Any]] = []
    cursor = ""
    while len(channels) < limit:
        form: dict[str, Any] = {
            "types": "public_channel,private_channel",
            "exclude_archived": "true",
            "limit": "200",
        }
        if cursor:
            form["cursor"] = cursor
        data = await slack_call("conversations.list", token=token, form=form)
        channels.extend(data.get("channels") or [])
        cursor = ((data.get("response_metadata") or {}).get("next_cursor") or "").strip()
        if not cursor:
            break
    return channels[:limit]
