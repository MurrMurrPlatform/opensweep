"""Celery beat tick — dispatch Runs for Investigations with due cron schedules."""

from __future__ import annotations

from celery_app import app
from logging_config import logger


@app.task(name="opensweep.investigations.schedule_tick")
def schedule_tick() -> dict:
    from domains.investigations.services.schedule_scanner import scan_and_dispatch
    from infrastructure.celery_async import run_async_task
    from infrastructure.neomodel_config import configure_neomodel

    configure_neomodel()

    async def _go():
        # run_async_task reconnected the async neomodel driver to this
        # task's fresh event loop (infrastructure/celery_async.py).
        result = await scan_and_dispatch()
        return {
            "scanned": result.scanned,
            "dispatched": result.dispatched,
            "skipped_invalid": result.skipped_invalid,
            "errors": result.errors,
        }

    out = run_async_task(_go)
    logger.info(f"schedule tick: {out}", extra={"tag": "schedule"})
    return out
