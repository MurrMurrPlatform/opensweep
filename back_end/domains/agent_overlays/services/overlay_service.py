"""Org agent overlay service — org-scoped CRUD, append-only revisions, revert.

Tenancy: every read and write is keyed by the caller's org_uid; an overlay is
only ever visible to (and editable by) its owning org. Any org member may
write (spec decision 5) — the compensating guardrails are attribution
(updated_by + timestamps), the append-only revision history, and audit
events on every mutation.

Uniqueness: one overlay per (org_uid, playbook), enforced here with a
per-key asyncio.Lock around get-or-create (neomodel has no composite unique
indexes; same pattern as run_dispatch._DISPATCH_LOCKS).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException

from domains.agent_overlays.models import (
    OVERLAY_BODY_MAX_BYTES,
    OVERLAY_MODES,
    OrgAgentOverlay,
    OrgAgentOverlayRevision,
)
from domains.agent_overlays.schemas import (
    OverlayDTO,
    OverlayRevisionDTO,
    PlatformBaseDTO,
    PlaybookOverlayStatusDTO,
)
from domains.agent_prompts.services.seed_agent_bases import AGENT_PLAYBOOKS
from infrastructure.audit import write_audit
from logging_config import logger

# Per-process, per-(org, playbook) upsert locks. Entries are never evicted —
# the population (org × the AGENT_PLAYBOOKS under active editing) is small.
_UPSERT_LOCKS: dict[tuple[str, str], asyncio.Lock] = {}


def require_org(org_uid: str) -> str:
    org = (org_uid or "").strip()
    if not org:
        raise HTTPException(
            status_code=422,
            detail="agent overlays are org-scoped — your user has no organization",
        )
    return org


def validate_playbook(playbook: str) -> str:
    # AGENT_PLAYBOOKS, not investigations PLAYBOOKS: the overlayable agents
    # include the sweep flows (deep-scan, generate-docs) that run under the
    # "ask" run playbook but carry their own instruction bases.
    pb = (playbook or "").strip()
    if pb not in AGENT_PLAYBOOKS:
        raise HTTPException(
            status_code=422,
            detail=f"unknown playbook {playbook!r}; valid: {sorted(AGENT_PLAYBOOKS)}",
        )
    return pb


def validate_mode_and_body(mode: str, body: str) -> tuple[str, str]:
    m = (mode or "").strip().lower()
    if m not in OVERLAY_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid mode {mode!r}; valid: {sorted(OVERLAY_MODES)}",
        )
    b = body or ""
    if len(b.encode("utf-8")) > OVERLAY_BODY_MAX_BYTES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"overlay body exceeds the {OVERLAY_BODY_MAX_BYTES // 1024} KB limit "
                f"({len(b.encode('utf-8'))} bytes) — trim the guidance"
            ),
        )
    return m, b


def overlay_to_dto(node: OrgAgentOverlay) -> OverlayDTO:
    return OverlayDTO(
        uid=node.uid,
        playbook=node.playbook or "",
        mode=node.mode or "append",
        body=node.body or "",
        enabled=bool(node.enabled),
        rev=int(node.rev or 0),
        updated_by=node.updated_by or "",
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


async def get_overlay(org_uid: str, playbook: str) -> OrgAgentOverlay | None:
    """The org's overlay for a playbook (enabled or not); None when unset."""
    rows = await OrgAgentOverlay.nodes.filter(org_uid=org_uid, playbook=playbook)
    return rows[0] if rows else None


async def resolve_enabled_overlay(org_uid: str, playbook: str) -> OrgAgentOverlay | None:
    """The ENABLED overlay for composition — never raises (a dangling or
    broken overlay must degrade to the platform base, not fail a run)."""
    if not (org_uid or "").strip():
        return None
    try:
        node = await get_overlay(org_uid, playbook)
    except Exception as exc:  # noqa: BLE001 — resolution failure never fails a run
        logger.warning(
            f"org overlay resolution failed ({org_uid}/{playbook}): "
            f"{type(exc).__name__}: {exc}",
            extra={"tag": "agent_overlays"},
        )
        return None
    if node is None or not node.enabled or not (node.body or "").strip():
        return None
    return node


async def active_overlay_provenance(org_uid: str, playbook: str) -> tuple[str, int]:
    """(overlay_uid, rev) of the active overlay at dispatch — ("", 0) when
    none applies. Never raises."""
    node = await resolve_enabled_overlay(org_uid, playbook)
    if node is None:
        return "", 0
    return node.uid, int(node.rev or 0)


async def _next_rev(org_uid: str, playbook: str) -> int:
    """Monotonic per (org, playbook), across deletes: max stored rev + 1."""
    revisions = await OrgAgentOverlayRevision.nodes.filter(
        org_uid=org_uid, playbook=playbook
    )
    head = max((int(r.rev or 0) for r in revisions), default=0)
    return head + 1


async def _save_overlay(
    *,
    org_uid: str,
    playbook: str,
    mode: str,
    body: str,
    enabled: bool,
    actor_uid: str,
    audit_kind: str,
    audit_extra: dict | None = None,
) -> OrgAgentOverlay:
    """Shared write path for upsert and revert: get-or-create under the
    per-(org, playbook) lock, bump rev, snapshot a revision, audit."""
    lock = _UPSERT_LOCKS.setdefault((org_uid, playbook), asyncio.Lock())
    async with lock:
        now = datetime.now(UTC)
        node = await get_overlay(org_uid, playbook)
        if node is None:
            node = OrgAgentOverlay(
                uid=uuid4().hex,
                org_uid=org_uid,
                playbook=playbook,
                created_at=now,
            )
        node.mode = mode
        node.body = body
        node.enabled = enabled
        node.updated_by = actor_uid or ""
        node.rev = await _next_rev(org_uid, playbook)
        node.updated_at = now
        await node.save()
        revision = OrgAgentOverlayRevision(
            uid=uuid4().hex,
            overlay_uid=node.uid,
            org_uid=org_uid,
            playbook=playbook,
            rev=int(node.rev),
            mode=mode,
            body=body,
            enabled=enabled,
            author_uid=actor_uid or "",
            created_at=now,
        )
        await revision.save()
    await write_audit(
        kind=audit_kind,
        subject_uid=node.uid,
        subject_type="OrgAgentOverlay",
        actor_uid=actor_uid or "",
        payload={
            "org_uid": org_uid,
            "playbook": playbook,
            "mode": mode,
            "enabled": enabled,
            "rev": int(node.rev),
            "body_bytes": len((body or "").encode("utf-8")),
            **(audit_extra or {}),
        },
    )
    return node


async def upsert_overlay(
    *,
    org_uid: str,
    playbook: str,
    mode: str,
    body: str,
    enabled: bool = True,
    actor_uid: str = "",
) -> OrgAgentOverlay:
    org = require_org(org_uid)
    pb = validate_playbook(playbook)
    m, b = validate_mode_and_body(mode, body)
    return await _save_overlay(
        org_uid=org,
        playbook=pb,
        mode=m,
        body=b,
        enabled=bool(enabled),
        actor_uid=actor_uid,
        audit_kind="agent_overlay.updated",
    )


async def delete_overlay(*, org_uid: str, playbook: str, actor_uid: str = "") -> None:
    """Remove the overlay (restore platform default). Revision history is
    kept — it is keyed by (org, playbook), so a later save or revert resumes
    the same monotonic rev sequence."""
    org = require_org(org_uid)
    pb = validate_playbook(playbook)
    node = await get_overlay(org, pb)
    if node is None:
        raise HTTPException(status_code=404, detail=f"no overlay set for playbook {pb!r}")
    last_rev = int(node.rev or 0)
    deleted_uid = node.uid
    await node.delete()
    await write_audit(
        kind="agent_overlay.deleted",
        subject_uid=deleted_uid,
        subject_type="OrgAgentOverlay",
        actor_uid=actor_uid or "",
        payload={"org_uid": org, "playbook": pb, "rev": last_rev},
    )


async def list_revisions(org_uid: str, playbook: str) -> list[OverlayRevisionDTO]:
    org = require_org(org_uid)
    pb = validate_playbook(playbook)
    revisions = await OrgAgentOverlayRevision.nodes.filter(org_uid=org, playbook=pb)
    revisions.sort(key=lambda r: int(r.rev or 0), reverse=True)
    return [
        OverlayRevisionDTO(
            uid=r.uid,
            playbook=r.playbook or pb,
            rev=int(r.rev or 0),
            mode=r.mode or "append",
            body=r.body or "",
            enabled=bool(r.enabled),
            author_uid=r.author_uid or "",
            created_at=r.created_at,
        )
        for r in revisions
    ]


async def revert_overlay(
    *, org_uid: str, playbook: str, rev: int, actor_uid: str = ""
) -> OrgAgentOverlay:
    """Revert = save a NEW head revision copying an old one (append-only)."""
    org = require_org(org_uid)
    pb = validate_playbook(playbook)
    revisions = await OrgAgentOverlayRevision.nodes.filter(org_uid=org, playbook=pb)
    source = next((r for r in revisions if int(r.rev or 0) == int(rev)), None)
    if source is None:
        raise HTTPException(
            status_code=404,
            detail=f"revision {rev} not found for playbook {pb!r}",
        )
    return await _save_overlay(
        org_uid=org,
        playbook=pb,
        mode=source.mode or "append",
        body=source.body or "",
        enabled=True,
        actor_uid=actor_uid,
        audit_kind="agent_overlay.reverted",
        audit_extra={"reverted_to_rev": int(rev)},
    )


async def list_playbook_statuses(org_uid: str) -> list[PlaybookOverlayStatusDTO]:
    """Every playbook with its platform base preview + overlay status."""
    from domains.agent_prompts.services.seed_agent_bases import (
        AGENT_PLAYBOOKS,
        agent_base_prompt,
        agent_source_url,
    )

    org = require_org(org_uid)
    out: list[PlaybookOverlayStatusDTO] = []
    for playbook in AGENT_PLAYBOOKS:
        base = None
        try:
            row = await agent_base_prompt(playbook)
            if row is not None:
                base = PlatformBaseDTO(
                    uid=row.uid,
                    title=row.title or "",
                    body=row.body or "",
                    enabled=bool(row.enabled),
                    source_url=row.source_url or agent_source_url(playbook),
                )
        except Exception as exc:  # noqa: BLE001 — listing degrades, never 500s
            logger.warning(
                f"platform base lookup failed for {playbook}: {exc}",
                extra={"tag": "agent_overlays"},
            )
        overlay = await get_overlay(org, playbook)
        out.append(
            PlaybookOverlayStatusDTO(
                playbook=playbook,
                platform=base,
                overlay=overlay_to_dto(overlay) if overlay else None,
            )
        )
    return out
