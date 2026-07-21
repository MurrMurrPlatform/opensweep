"""Celery task — execute a QUEUED run's dispatch pipeline in its own task.

Run dispatch (clone → RUNNING → agent turn) can take an hour for CLI runs, far
beyond the 600/900s limits on the beat ticks (campaign tick, auto-audit,
schedule tick) that create the queued row. Those ticks therefore hand off to
this per-run task instead of running the pipeline inline: an in-loop asyncio
task would be cancelled the instant the tick's `asyncio.run` loop closes,
leaving the run stuck QUEUED. Mirrors `resume_run` (tasks/resume_paused.py) —
per-run task, extended time limits, its own event loop for the whole run.
"""

from __future__ import annotations

from celery_app import app
from logging_config import logger


@app.task(
    name="opensweep.runs.dispatch_run",
    soft_time_limit=3600,
    time_limit=3900,
)
def dispatch_run(run_uid: str) -> dict:
    """Dispatch ONE queued run — may execute a full CLI run, hence the per-task
    3600/3900s limits overriding the global 600/900s."""
    from infrastructure.celery_async import run_async_task
    from infrastructure.neomodel_config import configure_neomodel

    configure_neomodel()

    async def _go() -> dict:
        from domains.runs.services.lifecycle import execute_queued_run

        return await execute_queued_run(run_uid)

    out = run_async_task(_go)
    logger.info(f"dispatch run {run_uid}: {out}", extra={"tag": "lifecycle"})
    return out
