"""Shared upsert for platform-seeded system Agents (bases + stage defaults +
variants).

The three seeders install `provenance="system"` rows keyed by a stable
`source_url`. This module is the single place that decides, per SeedMode,
whether an existing row is created, refreshed, or preserved — so the
seeders can never drift in how they treat re-seeds.

Platform-owned fields (title, description, prompt, produces, effort, tags)
are hashed into `seed_checksum` on write. On a SYNC re-seed a row whose
current content still hashes to its stored checksum is provably untouched
since we last seeded it, so it is safe to roll forward to newly shipped
content; any other row is a user edit and is preserved. See SeedMode.

Seed specs keep a `body` key for the instructions text (it maps onto
`Agent.prompt`).
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from domains.agents.models import Agent
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
# listed (enabled, provenance, created_at, uid …) is never touched on re-seed.
_OWNED_FIELDS = (
    "title",
    "description",
    "prompt",
    "produces",
    "default_effort",
    "tags",
)


def _normalized(spec: dict[str, Any]) -> dict[str, Any]:
    """Fill a partial seed spec with the model defaults for owned fields, so
    the checksum is computed over the exact values that get written."""
    return {
        "title": spec.get("title", ""),
        "description": spec.get("description", ""),
        "prompt": spec.get("body", spec.get("prompt", "")),
        "produces": spec.get("produces", "findings"),
        "default_effort": spec.get("default_effort", "normal"),
        "tags": list(spec.get("tags", [])),
    }


def _checksum(values: dict[str, Any]) -> str:
    return content_hash(
        values["title"],
        values["description"],
        values["prompt"],
        values["produces"],
        values["default_effort"],
        # tags order is meaningful to the hash but not to behavior; the specs
        # list them deterministically so this is stable.
        ",".join(values["tags"]),
    )


def _apply(row: Agent, values: dict[str, Any]) -> None:
    for f in _OWNED_FIELDS:
        setattr(row, f, values[f])
    row.seed_checksum = _checksum(values)


async def upsert_platform_prompt(
    spec: dict[str, Any],
    source_url: str,
    mode: SeedMode,
    *,
    existing: Optional[Agent] = None,
) -> str:
    """Create or reconcile one system Agent. Returns the action taken:
    "created" | "updated" | "unchanged" | "preserved".

    `existing` lets the caller pass a row it already looked up (avoids an
    extra query when it holds the source_url→row map); when None we resolve it.
    """
    values = _normalized(spec)
    shipped = _checksum(values)

    if existing is None:
        existing = next(
            iter(await Agent.nodes.filter(provenance="system", source_url=source_url)),
            None,
        )

    if existing is None:
        row = Agent(
            uid=uuid4().hex,
            provenance="system",
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
        # Untracked (seeded before checksums, hand-created, or freshly
        # migrated from the pre-Agent schema — m0008 clears checksums). We
        # can only adopt it as platform-owned when it already matches the
        # shipped content — otherwise we cannot tell a stale default from a
        # user edit, so we leave it and its empty checksum alone (preserved).
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


def _current_values(row: Agent) -> dict[str, Any]:
    return {
        "title": row.title or "",
        "description": row.description or "",
        "prompt": row.prompt or "",
        "produces": row.produces or "findings",
        "default_effort": row.default_effort or "normal",
        "tags": list(row.tags or []),
    }
