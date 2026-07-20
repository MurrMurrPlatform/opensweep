"""Campaign lifecycle: create (plan), launch, cancel, read.

Planning loads the repository, its docs, the live file tree, and the lens
catalog, then hands the pure planner the partition work. Tree resolution
degrades to watch-path-only areas on ANY failure — planning never fails
because GitHub was unreachable. Status only moves through the legality
matrix; every mutation appends a timeline event with the same
refetch-before-save discipline as thread_service.record_event.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException

from domains.campaigns.models import (
    CAMPAIGN_TEMPLATES,
    Campaign,
    is_legal_status_transition,
)
from domains.campaigns.schemas import CampaignDTO, CreateCampaignRequest
from domains.campaigns.services import planner
from infrastructure.audit import write_audit
from logging_config import logger


def to_dto(c: Campaign) -> CampaignDTO:
    return CampaignDTO(
        uid=c.uid,
        repository_uid=c.repository_uid,
        title=c.title or "",
        status=c.status or "planning",
        template=c.template or "rotation",
        effort=c.effort or "",
        lens_keys=list(c.lens_keys or []),
        parts=[dict(p) for p in (c.parts or [])],
        max_parallel=int(c.max_parallel or 2),
        created_by=c.created_by or "",
        trigger_provenance=c.trigger_provenance or "",
        summary=dict(c.summary or {}),
        events=list(c.events or []),
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


async def get(uid: str) -> Campaign:
    c = await Campaign.nodes.get_or_none(uid=uid)
    if c is None:
        raise HTTPException(status_code=404, detail=f"Campaign {uid} not found")
    return c


async def list_for_repo(repository_uid: str) -> list[Campaign]:
    rows = await Campaign.nodes.filter(repository_uid=repository_uid)
    rows = list(rows)
    rows.sort(key=lambda c: c.created_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    return rows


async def record_event(campaign: Campaign, type: str, **payload) -> None:
    # ALWAYS reload before appending (thread_service.record_event): neomodel
    # save() writes EVERY declared property, so saving a stale node clobbers
    # fields written in between — parts/status updated by a concurrent tick.
    now = datetime.now(UTC)
    fresh = await Campaign.nodes.get_or_none(uid=campaign.uid) or campaign
    fresh.events = [
        *(fresh.events or []),
        {"ts": now.isoformat(), "type": type, **payload},
    ]
    fresh.updated_at = now
    await fresh.save()
    if fresh is not campaign:
        campaign.events = fresh.events
        campaign.status = fresh.status
        campaign.parts = fresh.parts
        campaign.updated_at = fresh.updated_at


async def _file_tree_paths(repo) -> tuple[list[str], str]:
    """(blob paths at the default branch head, degraded_reason — "" = full).

    Empty paths + a reason on ANY failure (missing provider, no head sha,
    network) — the plan degrades to watch-path-only areas instead of
    failing. A truncated tree (very large repo) keeps the partial paths but
    still carries a reason: file counts and the remainder part are computed
    against a partial universe, and the plan must say so."""
    from infrastructure.git_providers import get_provider_client

    try:
        client = get_provider_client(repo)
        if not (client.is_active and repo.github_owner and repo.github_repo):
            logger.warning(
                f"campaign planning: no active git provider for {repo.uid} — "
                "planning from watch paths only",
                extra={"tag": "campaigns"},
            )
            return [], "no active git provider connection"
        sha = await client.get_branch_head_sha(
            repo.github_owner, repo.github_repo, repo.default_branch or "main"
        )
        if not sha:
            logger.warning(
                f"campaign planning: no head sha for {repo.uid} — "
                "planning from watch paths only",
                extra={"tag": "campaigns"},
            )
            return [], f"no head sha for branch {repo.default_branch or 'main'}"
        tree = await client.get_tree(repo.github_owner, repo.github_repo, sha)
        paths = [str(p) for p in (tree.get("paths") or [])]
        if tree.get("truncated"):
            logger.warning(
                f"campaign planning: tree truncated for {repo.uid} "
                f"({len(paths)} paths) — plan covers a partial file list",
                extra={"tag": "campaigns"},
            )
            return paths, "file tree truncated (very large repo) — partial file list"
        return paths, ""
    except Exception as exc:  # noqa: BLE001 — degrade, never fail planning
        logger.warning(
            f"campaign planning: tree unavailable for {repo.uid}: "
            f"{type(exc).__name__}: {exc}",
            extra={"tag": "campaigns"},
        )
        return [], f"file tree unavailable ({type(exc).__name__})"


async def create(
    repository_uid: str,
    req: CreateCampaignRequest,
    *,
    created_by: str = "",
    trigger_provenance: str = "manual",
) -> Campaign:
    """Plan a campaign (status=planning — launch is the separate go signal)."""
    from domains.docs.models import Doc
    from domains.lenses.services import lens_service
    from domains.repositories.models import Repository
    from domains.runs.services.audit_selection import coverage_recency_for

    template = (req.template or "rotation").strip()
    if template not in CAMPAIGN_TEMPLATES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid template {req.template!r}; valid: {sorted(CAMPAIGN_TEMPLATES)}",
        )
    repo = await Repository.nodes.get_or_none(uid=repository_uid)
    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repository {repository_uid} not found")
    if template == "focused" and not req.lens_keys:
        raise HTTPException(
            status_code=422, detail="focused campaigns need lens_keys[0] as the focus lens"
        )

    docs = [d for d in await Doc.nodes.all() if d.repository_uid == repository_uid]
    file_paths, degraded_reason = await _file_tree_paths(repo)

    lenses = [
        {
            "key": lens.key,
            "scope": lens.scope or "local",
            "global_agent_key": lens.global_agent_key or "",
            "enabled": bool(lens.enabled),
        }
        for lens in await lens_service.list_lenses(enabled_only=True)
    ]
    if req.lens_keys:
        wanted = set(req.lens_keys)
        lenses = [lens for lens in lenses if lens["key"] in wanted]

    areas = planner.normalize_areas(
        [
            {
                "uid": d.uid,
                "slug": d.slug or "",
                "title": d.title or "",
                "watch_paths": list(d.watch_paths or []),
            }
            for d in docs
        ],
        file_paths,
    )
    path_recency = None
    if template == "rotation":
        path_recency = await coverage_recency_for(repository_uid)
    parts = planner.build_plan(
        template,
        areas,
        lenses,
        k=req.k,
        path_recency=path_recency,
        focus_lens=req.lens_keys[0] if template == "focused" and req.lens_keys else None,
    )

    c = Campaign(
        uid=uuid4().hex,
        repository_uid=repository_uid,
        title=req.title or f"{template.capitalize()} audit campaign",
        status="planning",
        template=template,
        effort=(req.effort or "").strip(),
        lens_keys=list(req.lens_keys or []),
        parts=parts,
        max_parallel=max(int(req.max_parallel or 2), 1),
        created_by=created_by,
        trigger_provenance=trigger_provenance or "manual",
    )
    await c.save()
    # A degraded plan (no/partial file tree) must be distinguishable from a
    # real one — users approve the plan's scope, so mark it on the record.
    planned_payload = {"parts": len(parts)}
    if degraded_reason:
        planned_payload["degraded"] = degraded_reason
    await record_event(c, "planned", **planned_payload)
    await write_audit(
        kind="campaign.planned",
        subject_uid=c.uid,
        subject_type="Campaign",
        actor_uid=created_by,
        repository_uid=repository_uid,
        payload={"template": template, "parts": len(parts), **({"degraded": degraded_reason} if degraded_reason else {})},
    )
    return c


async def _transition(c: Campaign, to_status: str) -> None:
    if not is_legal_status_transition(c.status or "planning", to_status):
        raise HTTPException(
            status_code=409, detail=f"illegal transition {c.status} → {to_status}"
        )
    c.status = to_status
    await c.save()


async def launch(uid: str, *, actor_uid: str = "") -> Campaign:
    """planning → running; the celery tick starts dispatching parts."""
    c = await get(uid)
    await _transition(c, "running")
    await record_event(c, "launched", by=actor_uid)
    return c


async def cancel(uid: str, *, reason: str = "", actor_uid: str = "") -> Campaign:
    """planning/running → cancelled. In-flight child runs are left to
    finish on their own; parts stay as-is for the record."""
    c = await get(uid)
    await _transition(c, "cancelled")
    await record_event(c, "cancelled", reason=reason, by=actor_uid)
    return c
