"""Effort selector → seeded RunPolicy mapping (short/normal/deep/unlimited)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from domains.runs.schemas import Effort
from domains.run_policies.models import RunPolicy
from domains.run_policies.services.system_default import ensure_system_default

# The operational fields a tier seeds — also the match/roll-forward set for
# the legacy migration below.
_TIER_FIELDS = (
    "max_wall_seconds",
    "max_tool_turns",
    "max_files_touched",
    "max_continuation_passes",
)

# max_wall_seconds: 0 = explicitly no wall guard (see resolve_wall_ceiling);
# None on any other ceiling = no ceiling (continuation passes then run
# wall-limited only).
_EFFORT_POLICIES: dict[Effort, dict] = {
    Effort.SHORT: {
        "name": "opensweep-short",
        "description": "Short run: quick, bounded checks.",
        "max_wall_seconds": 900,
        "max_tool_turns": 50,
        "max_files_touched": 25,
        "max_continuation_passes": 1,
    },
    Effort.NORMAL: {
        "name": "opensweep-normal",
        "description": "Normal run: standard investigation ceilings.",
        "max_wall_seconds": 3600,
        "max_tool_turns": 200,
        "max_files_touched": 100,
        "max_continuation_passes": 3,
    },
    Effort.DEEP: {
        "name": "opensweep-deep",
        "description": "Deep run: whole-repo audits, generous ceilings.",
        "max_wall_seconds": 14400,
        "max_tool_turns": 3000,
        "max_files_touched": 10000,
        "max_continuation_passes": 8,
    },
    Effort.UNLIMITED: {
        "name": "opensweep-unlimited",
        "description": "Unlimited run: no ceilings — stop it from the UI.",
        "max_wall_seconds": 0,
        "max_tool_turns": None,
        "max_files_touched": None,
        "max_continuation_passes": None,
    },
}

# Old seeded rows (by name) whose values exactly match the legacy seed were
# never human-tuned: rename + roll them forward to the current tier config.
# Match dicts use only surviving operational fields — max_dollars is gone from
# the model, so matching on it would read None on every row and misclassify
# them all as human-tuned. Entries for the CURRENT names carry each tier's
# pre-max_continuation_passes seed so existing rows roll forward
# uid-preservingly and gain the new ceiling.
_LEGACY_POLICIES: dict[str, tuple[dict, Effort]] = {
    "opensweep-effort-quick": (
        {"max_wall_seconds": 120, "max_tool_turns": 20, "max_files_touched": 25},
        Effort.SHORT,
    ),
    "opensweep-effort-deep": (
        {"max_wall_seconds": 7200, "max_tool_turns": 1500, "max_files_touched": 10000},
        Effort.DEEP,
    ),
    "opensweep-short": (
        {"max_wall_seconds": 900, "max_tool_turns": 50, "max_files_touched": 25},
        Effort.SHORT,
    ),
    "opensweep-normal": (
        {"max_wall_seconds": 3600, "max_tool_turns": 200, "max_files_touched": 100},
        Effort.NORMAL,
    ),
    "opensweep-deep": (
        {"max_wall_seconds": 14400, "max_tool_turns": 3000, "max_files_touched": 10000},
        Effort.DEEP,
    ),
    "opensweep-unlimited": (
        {"max_wall_seconds": 0, "max_tool_turns": None, "max_files_touched": None},
        Effort.UNLIMITED,
    ),
}


async def ensure_policy_for_effort(effort: Effort) -> RunPolicy:
    config = _EFFORT_POLICIES[effort]
    migrated = await _migrate_legacy_policy(effort)
    if migrated is not None:
        return migrated
    existing = await _find_by_name(config["name"])
    if existing is not None:
        return existing

    base = await ensure_system_default()
    policy = RunPolicy(
        uid=uuid4().hex,
        name=config["name"],
        description=config["description"],
        max_wall_seconds=config["max_wall_seconds"],
        max_tool_turns=config["max_tool_turns"],
        max_files_touched=config["max_files_touched"],
        max_continuation_passes=config["max_continuation_passes"],
        cloud_allowed=base.cloud_allowed,
        local_only=base.local_only,
        allowed_executors=list(base.allowed_executors or []),
        dry_run=base.dry_run,
        warn_at_pct=base.warn_at_pct,
        daily_repo_run_count=base.daily_repo_run_count,
        daily_repo_wall_seconds=base.daily_repo_wall_seconds,
        daily_repo_dollars=base.daily_repo_dollars,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await policy.save()
    return policy


async def _migrate_legacy_policy(effort: Effort) -> RunPolicy | None:
    """Rename/roll forward an untouched legacy effort policy in place (uid —
    and therefore every run_policy_uid reference — is preserved). A row whose
    values already match the current config is returned as-is; a human-tuned
    row is left alone (caller seeds/uses the current-name policy)."""
    config = _EFFORT_POLICIES[effort]
    for legacy_name, (legacy_values, target) in _LEGACY_POLICIES.items():
        if target != effort:
            continue
        row = await _find_by_name(legacy_name)
        if row is None:
            continue
        untouched = all(
            getattr(row, field_name, None) == value
            for field_name, value in legacy_values.items()
        )
        current = all(
            getattr(row, field_name, None) == config[field_name]
            for field_name in _TIER_FIELDS
        )
        if legacy_name == config["name"] and current:
            return row  # already rolled forward
        if not untouched:
            if legacy_name == config["name"]:
                return row  # human-tuned current-name row: use as-is
            return None  # human-tuned old-name row: leave it; caller seeds the new policy
        row.name = config["name"]
        row.description = config["description"]
        for field_name in _TIER_FIELDS:
            setattr(row, field_name, config[field_name])
        row.updated_at = datetime.now(timezone.utc)
        await row.save()
        return row
    return None


async def _find_by_name(name: str) -> RunPolicy | None:
    for policy in await RunPolicy.nodes.all():
        if (policy.name or "") == name:
            return policy
    return None
