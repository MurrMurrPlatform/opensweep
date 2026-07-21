"""Platform tool: propose_area_edit — the agent's write path into the
Area map.

Area edits write platform state, not repository state, so the tool is
tracking-safe in every playbook including analyze-only — no change dial
involved: proposals always land as pending AreaEdits for human review.
"""

from __future__ import annotations

from typing import Any

from domains.areas.services import area_freshness, area_service


async def propose_area_edit(
    *,
    repository_uid: str,
    key: str,
    kind: str = "subsystem",
    title: str = "",
    scope_paths: list[str] | None = None,
    spec: str = "",
    rationale: str = "",
    doc_uids: list[str] | None = None,
    enabled: bool = True,
    source_run_uid: str = "",
    # The dispatcher/envelope injects `executor` (and other scope keys) on
    # every tool call uniformly — absorb it via **_; this tool doesn't use it.
    **_: Any,
) -> dict[str, Any]:
    """Propose one Area for the repository's area map. Kinds: "subsystem"
    (exclusive partition — every auditable file belongs to exactly one
    subsystem leaf), "feature" (spec-anchored cross-cutting overlay), or
    "ignore" (non-auditable files; the spec must state WHY). Keys are
    path-like — "backend/delivery/convergence" nests under backend/delivery,
    and files belong to leaf areas only. An unknown key proposes a new area;
    an existing key proposes a full replacement of it (kind, title,
    scope_paths, spec, doc_uids). Lands as a pending edit for human review —
    keep specs small and set scope_paths to the repository paths the area
    covers so code changes there mark it for review. Pass enabled=false to
    propose RETIRING an area that should no longer exist. The result's
    `warnings` list the partition conflicts your proposal would create
    (against the live map and your own earlier proposals this run) —
    resolve them by re-proposing before you finish."""
    return await area_service.propose_area_edit(
        repository_uid=repository_uid,
        proposed_spec=spec,
        rationale=rationale,
        key=key,
        kind=kind,
        enabled=enabled,
        title=title,
        scope_paths=scope_paths,
        doc_uids=doc_uids,
        source_run_uid=source_run_uid or "",
    )


async def confirm_area_current(
    *,
    repository_uid: str,
    key: str,
    **_: Any,
) -> dict[str, Any]:
    """You verified this area is still correctly partitioned against the
    current code (its scope_paths and kind still hold) and it needs no edit:
    stamp the review so its stale flag clears. Only call this after actually
    checking the area — never to silence a stale marker you did not verify."""
    a = await area_freshness.confirm_area_current(repository_uid, key)
    if a is None:
        return {"status": "not_found", "key": key}
    return {"status": "ok", "key": a.key}
