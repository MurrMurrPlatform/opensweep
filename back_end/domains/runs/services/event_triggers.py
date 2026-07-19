"""Event triggers.

When a commit lands, Investigations with an `on-event` schedule whose
target paths overlap the touched paths become eligible (an empty
`target.paths` means repo-wide: eligible on any change). Whether an
eligible Investigation actually runs is its own `compute_dial`:

    disabled / suggest / ask-before-run  → candidate only (never auto-run)
    auto-run-cheap                       → run when the active provider is local (free)
    auto-run-any                         → always run

The GitHub push webhook calls `auto_run_candidates_for_change` with the
payload's changed paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domains.docs.services.doc_freshness import watches_path
from domains.runs.models import Investigation
from domains.runs.schemas import Executor
from domains.run_policies.services.dry_run import estimate as estimate_run
from logging_config import logger


@dataclass
class TriggerCandidate:
    investigation_uid: str
    investigation_title: str
    matched_paths: list[str]
    reason: str
    estimates: dict[str, dict[str, Any]]  # executor name → DryRunEstimate.to_dict()


async def candidates_for_change(
    *,
    repository_uid: str,
    changed_paths: list[str],
    executors_to_estimate: tuple[Executor, ...] = (
        Executor.INTERNAL_LLM,
        Executor.CLAUDE_CODE,
    ),
) -> list[TriggerCandidate]:
    """Find Investigations eligible to run after the given changes."""
    changed = [p for p in (str(p).strip() for p in changed_paths) if p]
    if not changed:
        return []

    invs = [
        i
        for i in await Investigation.nodes.all()
        if i.repository_uid == repository_uid and i.schedule == "on-event"
    ]
    out: list[TriggerCandidate] = []
    for i in invs:
        target_paths = [
            str(p) for p in ((i.target or {}).get("paths") or []) if str(p).strip()
        ]
        if target_paths:
            matched = [p for p in changed if watches_path(target_paths, p)]
            if not matched:
                continue
            reason = f"Investigation scoped to changed path(s) {matched[:3]}"
        else:
            matched = changed
            reason = "Repo-wide on-event Investigation (no path scoping)"
        estimates: dict[str, dict[str, Any]] = {}
        for ex in executors_to_estimate:
            est = estimate_run(
                executor=ex,
                intent=i.intent,
                scope_paths=len(changed),
            )
            estimates[ex.value] = est.to_dict()
        out.append(
            TriggerCandidate(
                investigation_uid=i.uid,
                investigation_title=i.title or i.intent[:60],
                matched_paths=matched[:20],
                reason=reason,
                estimates=estimates,
            )
        )
    return out


_AUTO_RUN_DIALS = {"auto-run-cheap", "auto-run-any"}


async def _dial_allows_run(dial: str, repository_uid: str) -> bool:
    if dial == "auto-run-any":
        return True
    if dial == "auto-run-cheap":
        # Cheap = the provider the run would use runs locally (unmetered).
        from domains.llm_providers.services.llm_executor import is_local_provider_kind
        from domains.llm_providers.services.llm_provider_service import (
            repository_org_uid,
            select_provider,
        )

        provider = await select_provider(org_uid=await repository_org_uid(repository_uid))
        return provider is not None and is_local_provider_kind(provider.kind or "")
    return False


async def auto_run_candidates_for_change(
    *, repository_uid: str, changed_paths: list[str]
) -> list[str]:
    """Dispatch eligible on-event Investigations whose compute_dial allows
    auto-running. Returns the dispatched run uids. Per-candidate failures
    (in-flight guards, no provider) are logged and skipped — one bad
    Investigation never blocks the rest."""
    from domains.runs.services.active_runs import active_runs_for
    from domains.runs.services.lifecycle import LifecycleError, trigger_run
    from domains.runs.schemas import RunTrigger

    candidates = await candidates_for_change(
        repository_uid=repository_uid,
        changed_paths=changed_paths,
        executors_to_estimate=(),
    )
    dispatched: list[str] = []
    for c in candidates:
        inv = await Investigation.nodes.get_or_none(uid=c.investigation_uid)
        if inv is None or (inv.compute_dial or "") not in _AUTO_RUN_DIALS:
            continue
        if not await _dial_allows_run(inv.compute_dial or "", repository_uid):
            continue
        in_flight = await active_runs_for(repository_uid=repository_uid)
        if any(r.investigation_uid == inv.uid for r in in_flight):
            continue  # this Investigation is already running
        try:
            run = await trigger_run(
                investigation_uid=inv.uid,
                trigger=RunTrigger.EVENT,
                triggered_by="on-event",
            )
            dispatched.append(run.uid)
        except LifecycleError as exc:
            logger.warning(
                f"on-event auto-run skipped for investigation {inv.uid}: {exc}",
                extra={"tag": "event-triggers"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"on-event auto-run failed for investigation {inv.uid}: "
                f"{type(exc).__name__}: {exc}",
                extra={"tag": "event-triggers"},
            )
    return dispatched


async def refresh_docs_for_change(
    *, repository_uid: str, changed_paths: list[str], source: str = ""
) -> None:
    """Tie a set of changed paths to doc upkeep: mark the watching Doc pages
    stale, then auto-run any on-event doc Investigations the compute_dial
    permits. Shared by the GitHub push webhook and the write-run finalize so
    freshness fires the moment code changes — whether the change arrives as a
    redelivered push or as a run that just pushed. Best-effort: never raises.

    Idempotent across both callers: mark_docs_stale re-stamps harmlessly and
    auto_run_candidates_for_change skips Investigations already in flight, so
    the webhook that follows a write-run push never double-dispatches.
    """
    changed = [p for p in (str(p).strip() for p in changed_paths) if p]
    if not changed:
        return
    label = f" ({source})" if source else ""
    try:
        from domains.docs.services.doc_freshness import mark_docs_stale

        stale = await mark_docs_stale(repository_uid, changed)
        if stale.docs_marked:
            logger.info(
                f"doc freshness{label}: {stale.docs_marked} pages marked stale "
                f"for {repository_uid}",
                extra={"tag": "freshness"},
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"doc freshness{label} failed for {repository_uid}: {exc}",
            extra={"tag": "freshness"},
        )
    try:
        dispatched = await auto_run_candidates_for_change(
            repository_uid=repository_uid, changed_paths=changed
        )
        if dispatched:
            logger.info(
                f"on-event auto-run{label} dispatched {len(dispatched)} run(s) "
                f"for {repository_uid}",
                extra={"tag": "event-triggers"},
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"on-event auto-run{label} failed for {repository_uid}: {exc}",
            extra={"tag": "event-triggers"},
        )
