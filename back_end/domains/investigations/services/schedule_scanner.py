"""Scan Investigations for due cron schedules and dispatch Runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from croniter import croniter

from domains.investigations.models import Investigation
from domains.investigations.schemas import RunTrigger, parse_schedule
from logging_config import logger


@dataclass
class ScanResult:
    scanned: int = 0
    dispatched: int = 0
    skipped_invalid: int = 0
    errors: list[str] = field(default_factory=list)


def is_due(expression: str, *, last: datetime | None, now: datetime) -> bool:
    """A cron is due if its previous fire time falls in (last, now]."""
    if not croniter.is_valid(expression):
        raise ValueError(f"invalid crontab: {expression!r}")
    prev_fire = croniter(expression, now).get_prev(datetime)
    if prev_fire.tzinfo is None:
        prev_fire = prev_fire.replace(tzinfo=timezone.utc)
    if last is None:
        return prev_fire <= now
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return prev_fire > last


def should_auto_audit(job_type: str, compute_dial: str) -> bool:
    """audit-stale Investigations fan out via run_auto_audit instead of a
    single trigger_run; `disabled` is the kill-safety even with a cron set."""
    return (job_type or "") == "audit-stale" and (compute_dial or "") != "disabled"


async def scan_and_dispatch(*, now: datetime | None = None) -> ScanResult:
    """Iterate Investigations with cron schedules and dispatch any that are due."""
    # Imported lazily so the pure is_due helper above stays importable without
    # pulling the full executor/config stack.
    from domains.investigations.services.lifecycle import LifecycleError, trigger_run

    moment = now or datetime.now(timezone.utc)
    result = ScanResult()
    for inv in await Investigation.nodes.all():
        schedule_raw = inv.schedule or ""
        try:
            kind, payload = parse_schedule(schedule_raw)
        except ValueError:
            result.skipped_invalid += 1
            continue
        if kind != "cron":
            continue
        result.scanned += 1
        try:
            due = is_due(payload, last=inv.last_scheduled_at, now=moment)
        except ValueError as exc:
            result.skipped_invalid += 1
            result.errors.append(f"{inv.uid}: {exc}")
            continue
        if not due:
            continue
        if (inv.job_type or "") == "audit-stale":
            # Staleness-driven fan-out (§F): one scoped audit per selected
            # page instead of a single run off this Investigation.
            if not should_auto_audit(inv.job_type or "", inv.compute_dial or ""):
                inv.last_scheduled_at = moment
                await inv.save()
                continue
            from domains.investigations.services.sweep import run_auto_audit

            try:
                audit = await run_auto_audit(
                    repository_uid=inv.repository_uid,
                    limit=int((inv.target or {}).get("limit") or 3),
                    triggered_by=f"cron:{payload}",
                )
            except Exception as exc:  # noqa: BLE001 — one bad repo never stops the scan
                result.errors.append(f"{inv.uid}: {type(exc).__name__}: {exc}")
                continue
            inv.last_scheduled_at = moment
            await inv.save()
            result.dispatched += len(audit.runs_dispatched)
            logger.info(
                f"schedule auto-audit inv={inv.uid} expr={payload} "
                f"dispatched={len(audit.runs_dispatched)}",
                extra={"tag": "schedule"},
            )
            continue
        try:
            await trigger_run(
                investigation_uid=inv.uid,
                trigger=RunTrigger.SCHEDULE,
                triggered_by=f"cron:{payload}",
            )
        except LifecycleError as exc:
            result.errors.append(f"{inv.uid}: {exc}")
            continue
        inv.last_scheduled_at = moment
        await inv.save()
        result.dispatched += 1
        logger.info(
            f"schedule dispatch inv={inv.uid} expr={payload}",
            extra={"tag": "schedule"},
        )
    return result
