"""Shared upsert for platform-seeded prompts (workflow defaults + variants).

Both seed_defaults.py and seed_variants.py install `source="platform"` rows
keyed by a stable `source_url`. This module is the single place that decides,
per SeedMode, whether an existing row is created, refreshed, or preserved —
so the two seeders can never drift in how they treat re-seeds.

Platform-owned fields (title, description, body, job type, scope, effort,
tags) are hashed into `seed_checksum` on write. On a SYNC re-seed a row whose
current content still hashes to its stored checksum is provably untouched
since we last seeded it, so it is safe to roll forward to newly shipped
content; any other row is a user edit and is preserved. See SeedMode.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from domains.agent_prompts.models import AgentPrompt
from infrastructure.seeding.base import SeedMode, SeedResult, content_hash


def tally(res: SeedResult, action: str) -> None:
    """Fold an upsert_platform_prompt action string into a SeedResult."""
    if action == "created":
        res.created += 1
    elif action == "updated":
        res.updated += 1
    elif action == "preserved":
        res.preserved += 1
    else:
        res.unchanged += 1

# Fields the platform owns and a SYNC is allowed to roll forward. Anything not
# listed (enabled, source, created_at, uid …) is never touched on re-seed.
_OWNED_FIELDS = (
    "title",
    "description",
    "body",
    "default_job_type",
    "default_scope",
    "default_effort",
    "tags",
)


def _normalized(spec: dict[str, Any]) -> dict[str, Any]:
    """Fill a partial seed spec with the model defaults for owned fields, so
    the checksum is computed over the exact values that get written."""
    return {
        "title": spec.get("title", ""),
        "description": spec.get("description", ""),
        "body": spec.get("body", ""),
        "default_job_type": spec.get("default_job_type", "audit"),
        "default_scope": spec.get("default_scope", "repository"),
        "default_effort": spec.get("default_effort", "normal"),
        "tags": list(spec.get("tags", [])),
    }


def _checksum(values: dict[str, Any]) -> str:
    return content_hash(
        values["title"],
        values["description"],
        values["body"],
        values["default_job_type"],
        values["default_scope"],
        values["default_effort"],
        # tags order is meaningful to the hash but not to behavior; the specs
        # list them deterministically so this is stable.
        ",".join(values["tags"]),
    )


def _apply(row: AgentPrompt, values: dict[str, Any]) -> None:
    for f in _OWNED_FIELDS:
        setattr(row, f, values[f])
    row.seed_checksum = _checksum(values)


async def upsert_platform_prompt(
    spec: dict[str, Any],
    source_url: str,
    mode: SeedMode,
    *,
    existing: Optional[AgentPrompt] = None,
) -> str:
    """Create or reconcile one platform prompt. Returns the action taken:
    "created" | "updated" | "unchanged" | "preserved".

    `existing` lets the caller pass a row it already looked up (avoids an
    extra query when it holds the source_url→row map); when None we resolve it.
    """
    values = _normalized(spec)
    shipped = _checksum(values)

    if existing is None:
        existing = next(
            iter(await AgentPrompt.nodes.filter(source="platform", source_url=source_url)),
            None,
        )

    if existing is None:
        row = AgentPrompt(
            uid=uuid4().hex,
            source="platform",
            source_url=source_url,
            enabled=True,
            **values,
            seed_checksum=shipped,
        )
        await row.save()
        return "created"

    if mode is SeedMode.UPSERT:
        return "unchanged"

    current = _checksum(_current_values(existing))

    if mode is SeedMode.FORCE:
        # Overwrite to shipped regardless of who last touched the row. Compare
        # CURRENT content (not the stored checksum, which a user edit via the
        # API leaves stale) so a user edit that happens to match the row's old
        # seed hash is still reset.
        if current == shipped:
            if existing.seed_checksum != shipped:
                existing.seed_checksum = shipped
                await existing.save()
            return "unchanged"
        _apply(existing, values)
        await existing.save()
        return "updated"

    # SYNC: roll forward only rows we can prove the user hasn't edited.
    stored = existing.seed_checksum or ""
    if stored == "":
        # Untracked (seeded before checksums, or hand-created). We can only
        # adopt it as platform-owned when it already matches the shipped
        # content — otherwise we cannot tell a stale default from a user edit,
        # so we leave it and its empty checksum alone (preserved).
        if current == shipped:
            existing.seed_checksum = shipped
            await existing.save()
            return "unchanged"
        return "preserved"
    if stored != current:
        return "preserved"  # user edited since our last seed
    if current == shipped:
        return "unchanged"
    _apply(existing, values)
    await existing.save()
    return "updated"


def _current_values(row: AgentPrompt) -> dict[str, Any]:
    return {
        "title": row.title or "",
        "description": row.description or "",
        "body": row.body or "",
        "default_job_type": row.default_job_type or "audit",
        "default_scope": row.default_scope or "repository",
        "default_effort": row.default_effort or "normal",
        "tags": list(row.tags or []),
    }
