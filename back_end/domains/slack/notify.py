"""Outbound Slack notifications, hooked into the audit stream.

write_audit → notify_slack_of_event (sync, cheap prefilter, best-effort
Celery enqueue) → opensweep.slack.deliver_event (worker) → deliver_audit_event
(resolve org → connection → rules → post).

Delivery is fan-out per matching channel; a channel-level Slack failure is
logged and skipped so one archived channel can't starve the others.
"""

from __future__ import annotations

from typing import Any

from domains.slack.events import RELEVANT_AUDIT_KINDS, event_types_for
from logging_config import logger

DELIVER_TASK_NAME = "opensweep.slack.deliver_event"

# Runs on hidden surfaces (chat bubbles, @opensweep comment replies, Slack
# conversations) are conversational plumbing — notifying on them would echo
# every Slack question back as a "run completed" ping.
_NOTIFIABLE_RUN_SURFACES = {"runs"}


def notify_slack_of_event(
    *,
    kind: str,
    subject_uid: str,
    subject_type: str,
    actor_uid: str,
    repository_uid: str,
    payload: dict[str, Any],
) -> None:
    """Enqueue delivery for one audit event. Called from write_audit — must
    never raise and must stay cheap: irrelevant kinds and repo-less
    (platform-level) events return before touching the broker."""
    if kind not in RELEVANT_AUDIT_KINDS or not repository_uid:
        return
    try:
        from celery_app import app as celery_app

        celery_app.send_task(
            DELIVER_TASK_NAME,
            kwargs={
                "event": {
                    "kind": kind,
                    "subject_uid": subject_uid,
                    "subject_type": subject_type,
                    "actor_uid": actor_uid,
                    "repository_uid": repository_uid,
                    "payload": payload,
                }
            },
            retry=False,
        )
    except Exception as exc:  # noqa: BLE001 — notification loss must never break the flow
        logger.warning(f"Slack notify enqueue skipped ({kind}): {exc}", extra={"tag": "slack"})


async def _subject_context(subject_type: str, subject_uid: str) -> tuple[str, bool]:
    """(title, deliverable) for the event's subject. Runs on hidden surfaces
    are not deliverable; unresolvable subjects deliver with an empty title —
    except Run subjects, which fail CLOSED: skipping a rare notification
    beats echoing a Slack question back as a "run completed" ping."""
    if not subject_type or not subject_uid:
        return "", True
    try:
        if subject_type == "Run":
            from domains.investigations.models import Run

            run = await Run.nodes.get_or_none(uid=subject_uid)
            if run is None:
                return "", True
            if (run.surface or "runs") not in _NOTIFIABLE_RUN_SURFACES:
                return "", False
            return run.title or "", True
        if subject_type == "Ticket":
            from domains.tickets.models import Ticket

            node = await Ticket.nodes.get_or_none(uid=subject_uid)
            return (getattr(node, "title", "") or "") if node else "", True
        if subject_type == "Finding":
            from domains.findings.models import Finding

            node = await Finding.nodes.get_or_none(uid=subject_uid)
            return (getattr(node, "title", "") or "") if node else "", True
        if subject_type == "PullRequest":
            from domains.delivery.models import PullRequest

            node = await PullRequest.nodes.get_or_none(uid=subject_uid)
            return (getattr(node, "title", "") or "") if node else "", True
    except Exception as exc:  # noqa: BLE001 — context is decoration for non-Run subjects
        logger.warning(
            f"Slack subject context lookup failed for {subject_type} {subject_uid}: {exc}",
            extra={"tag": "slack"},
        )
        if subject_type == "Run":
            return "", False
    return "", True


async def deliver_audit_event(event: dict[str, Any]) -> dict[str, Any]:
    """Resolve and post one audit event to every matching channel.

    Returns a small stats dict (visible in the Celery result backend)."""
    from domains.repositories.models import Repository
    from domains.slack import service as slack_service
    from domains.slack.client import SlackApiError, post_message
    from domains.slack.formatting import format_event_message
    from domains.slack.models import SlackNotificationRule

    kind = str(event.get("kind") or "")
    repository_uid = str(event.get("repository_uid") or "")
    types = event_types_for(kind, event.get("payload") or {})
    if not types or not repository_uid:
        return {"delivered": 0, "skipped": "irrelevant"}

    repo = await Repository.nodes.get_or_none(uid=repository_uid)
    if repo is None or not repo.org_uid:
        return {"delivered": 0, "skipped": "no_repository"}

    connection = await slack_service.get_connection(repo.org_uid)
    if connection is None:
        return {"delivered": 0, "skipped": "not_connected"}

    rules = await SlackNotificationRule.nodes.filter(
        org_uid=repo.org_uid, event_type__in=types, enabled=True
    )
    rules = [r for r in rules if not r.repository_uid or r.repository_uid == repository_uid]
    if not rules:
        return {"delivered": 0, "skipped": "no_rules"}

    title, deliverable = await _subject_context(
        str(event.get("subject_type") or ""), str(event.get("subject_uid") or "")
    )
    if not deliverable:
        return {"delivered": 0, "skipped": "hidden_surface"}

    token = slack_service.bot_token(connection)
    delivered = 0
    errors: list[str] = []
    # One message per (event type, channel): a rule set routing the same kind
    # to the same channel twice (e.g. all-repos + this-repo) posts once.
    seen: set[tuple[str, str]] = set()
    for rule in rules:
        key = (rule.event_type, rule.channel_id)
        if key in seen:
            continue
        seen.add(key)
        text, blocks = format_event_message(
            rule.event_type, event, repo_slug=repo.slug or "", subject_title=title
        )
        try:
            await post_message(token, channel=rule.channel_id, text=text, blocks=blocks)
            delivered += 1
        except SlackApiError as exc:
            errors.append(f"{rule.channel_id}: {exc.error}")
            logger.warning(
                f"Slack delivery to {rule.channel_id} failed ({kind}): {exc.error}",
                extra={"tag": "slack"},
            )
    return {"delivered": delivered, "errors": errors}
