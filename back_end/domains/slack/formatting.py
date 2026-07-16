"""Block Kit rendering for outbound Slack notifications + markdown→mrkdwn.

Messages stay deliberately small: one header line (emoji + label + subject),
one context line (repo · actor), and an "Open in OpenSweep" link button when a
frontend base URL is configured. Everything degrades gracefully — a missing
title or unresolvable subject still renders a useful line.
"""

from __future__ import annotations

import re
from typing import Any

from config import settings
from domains.slack.events import BY_TYPE

# Where each subject type lives in the SPA (front_end/src/router/index.ts).
_SUBJECT_PATHS = {
    "Run": "/runs/{uid}",
    "Ticket": "/tickets/{uid}",
    "Finding": "/findings/{uid}",
    "PullRequest": "/pull-requests/{uid}",
    "Analysis": "/analyses/{uid}",
}


def frontend_base_url() -> str:
    """Deep-link origin: the SPA base, else the public backend origin (same
    origin in Caddy deployments), else "" (links omitted)."""
    base = (settings.OPENSWEEP_FRONTEND_BASE_URL or "").strip()
    if not base:
        base = (settings.OPENSWEEP_WEBHOOK_PUBLIC_BASE_URL or "").strip()
    return base.rstrip("/")


def subject_link(subject_type: str | None, subject_uid: str | None) -> str:
    base = frontend_base_url()
    path = _SUBJECT_PATHS.get(subject_type or "")
    if not base or not path or not subject_uid:
        return ""
    return base + path.format(uid=subject_uid)


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def format_event_message(
    event_type: str,
    event: dict[str, Any],
    *,
    repo_slug: str,
    subject_title: str = "",
) -> tuple[str, list[dict[str, Any]]]:
    """(fallback_text, blocks) for one audit event routed to Slack."""
    spec = BY_TYPE.get(event_type)
    label = spec.label if spec else event_type
    emoji = f":{spec.emoji}:" if spec else ":bell:"
    payload: dict[str, Any] = event.get("payload") or {}

    detail_bits: list[str] = []
    playbook = str(payload.get("playbook") or "")
    if playbook:
        detail_bits.append(playbook)
    severity = str(payload.get("severity") or "")
    if severity:
        detail_bits.append(f"severity {severity}")
    status = str(payload.get("to") or payload.get("status") or "")
    if event_type == "ticket.status_changed" and status:
        detail_bits.append(f"→ {status}")
    result = str(payload.get("result") or "")
    if event_type in {"review.completed", "attention.required"} and result:
        detail_bits.append(result.replace("_", " "))

    title = _truncate(subject_title or str(payload.get("title") or ""), 150)
    headline = f"{emoji} *{label}*"
    if title:
        headline += f" — {title}"
    if detail_bits:
        headline += f"  _({', '.join(detail_bits)})_"

    context_bits = [b for b in (repo_slug, str(event.get("actor_uid") or "")) if b]
    link = subject_link(event.get("subject_type"), event.get("subject_uid"))

    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": _truncate(headline, 2900)}}
    ]
    if context_bits:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": _truncate(" · ".join(context_bits), 2900)}],
            }
        )
    if link:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Open in OpenSweep"},
                        "url": link,
                    }
                ],
            }
        )

    fallback = f"{label}: {title}" if title else label
    if repo_slug:
        fallback += f" ({repo_slug})"
    return _truncate(fallback, 500), blocks


# ── markdown → Slack mrkdwn (best-effort, for chat replies) ─────────────────

_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_HEADER = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)

REPLY_CHAR_LIMIT = 8000  # comfortably under chat.postMessage's 40k ceiling


def to_mrkdwn(markdown: str) -> str:
    """Convert the common markdown Slack renders differently. Code fences and
    inline code pass through untouched (shared syntax)."""
    out = markdown
    out = _MD_LINK.sub(r"<\2|\1>", out)
    out = _MD_BOLD.sub(r"*\1*", out)
    out = _MD_HEADER.sub(r"*\1*", out)
    if len(out) > REPLY_CHAR_LIMIT:
        out = out[:REPLY_CHAR_LIMIT].rstrip() + "\n_… reply truncated — see the run in OpenSweep._"
    return out
