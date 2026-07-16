"""Single helper used by every state-changing service to record an audit event."""

import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from domains.events.models import Event
from logging_config import logger

# Subject labels whose nodes carry repository_uid (Repository maps to itself).
_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


async def _derive_repository_uid(subject_uid: str | None, subject_type: str | None) -> str:
    """Tenancy: resolve the subject's repository so audit events are
    org-scopeable. One indexed lookup; empty string = platform-level event."""
    if not subject_uid or not subject_type or not _LABEL_RE.match(subject_type):
        return ""
    if subject_type == "Repository":
        return subject_uid
    try:
        from neomodel import adb

        rows, _ = await adb.cypher_query(
            f"MATCH (n:{subject_type} {{uid: $uid}}) RETURN n.repository_uid",
            {"uid": subject_uid},
        )
        return str(rows[0][0]) if rows and rows[0][0] else ""
    except Exception:
        return ""


async def write_audit(
    *,
    kind: str,
    subject_uid: str | None = None,
    subject_type: str | None = None,
    actor_uid: str | None = None,
    payload: dict[str, Any] | None = None,
    repository_uid: str | None = None,
) -> None:
    """Best-effort: failures are logged but never raised, so audit writes can't break flows.

    repository_uid is derived from the subject node when not passed explicitly
    (Repository subjects map to themselves; other labels via their
    repository_uid property). Events that resolve to no repository are
    platform-level and surface to admins only.
    """
    try:
        repo_uid = (
            repository_uid
            if repository_uid is not None
            else await _derive_repository_uid(subject_uid, subject_type)
        )
        ev = Event(
            uid=uuid4().hex,
            kind=kind,
            subject_uid=subject_uid,
            subject_type=subject_type,
            actor_uid=actor_uid,
            repository_uid=repo_uid or "",
            payload=payload or {},
            occurred_at=datetime.now(timezone.utc),
        )
        await ev.save()
        try:
            # Per-org Slack notifications subscribe to the audit stream — one
            # choke point instead of instrumenting every call site. Cheap
            # prefilter + Celery enqueue; never allowed to fail the write.
            from domains.slack.notify import notify_slack_of_event

            notify_slack_of_event(
                kind=kind,
                subject_uid=subject_uid or "",
                subject_type=subject_type or "",
                actor_uid=actor_uid or "",
                repository_uid=repo_uid or "",
                payload=payload or {},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Slack notify hook skipped ({kind}): {exc}", extra={"tag": "audit"})
    except Exception as exc:
        logger.warning(f"Audit write skipped ({kind}): {exc}", extra={"tag": "audit"})
