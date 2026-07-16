"""Effort selector to RunPolicy mapping."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from domains.investigations.schemas import InvestigationEffort
from domains.run_policies.models import RunPolicy
from domains.run_policies.services.system_default import ensure_system_default


_EFFORT_POLICIES = {
    InvestigationEffort.QUICK: {
        "name": "opensweep-effort-quick",
        "description": "Quick investigation ceilings.",
        "max_dollars": 0.25,
        "max_wall_seconds": 120,
        "max_tool_turns": 20,
        "max_files_touched": 25,
    },
    InvestigationEffort.DEEP: {
        "name": "opensweep-effort-deep",
        "description": "Deep investigation ceilings.",
        "max_dollars": 25.0,
        "max_wall_seconds": 7200,
        "max_tool_turns": 1500,
        "max_files_touched": 10000,
    },
}


async def ensure_policy_for_effort(effort: InvestigationEffort) -> RunPolicy:
    if effort == InvestigationEffort.NORMAL:
        return await ensure_system_default()

    config = _EFFORT_POLICIES[effort]
    existing = await _find_by_name(config["name"])
    if existing is not None:
        return existing

    base = await ensure_system_default()
    policy = RunPolicy(
        uid=uuid4().hex,
        name=config["name"],
        description=config["description"],
        max_tokens=base.max_tokens,
        max_dollars=config["max_dollars"],
        max_wall_seconds=config["max_wall_seconds"],
        max_tool_turns=config["max_tool_turns"],
        max_files_touched=config["max_files_touched"],
        max_test_seconds=base.max_test_seconds,
        cloud_allowed=base.cloud_allowed,
        local_only=base.local_only,
        allowed_executors=list(base.allowed_executors or []),
        dry_run=base.dry_run,
        warn_at_pct=base.warn_at_pct,
        on_exceed=base.on_exceed,
        daily_repo_run_count=base.daily_repo_run_count,
        daily_repo_wall_seconds=base.daily_repo_wall_seconds,
        daily_repo_dollars=base.daily_repo_dollars,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await policy.save()
    return policy


async def _find_by_name(name: str) -> RunPolicy | None:
    for policy in await RunPolicy.nodes.all():
        if (policy.name or "") == name:
            return policy
    return None

