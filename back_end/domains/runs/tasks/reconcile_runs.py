"""Celery beat tick — repair Run rows whose dispatching process died.

Dispatch is an in-process asyncio task (backend or worker), so a crash leaves
the row `queued`/`running` forever. The startup sweeps (app.py lifespan,
celery_app worker_ready) catch clean restarts immediately; this tick is the
backstop for everything else: hung executors, killed containers, and rows
from before the dispatch_runtime stamp existed.
"""

from __future__ import annotations

from celery_app import app
from logging_config import logger


@app.task(name="opensweep.runs.reconcile_stale_runs")
def reconcile_stale_runs_task() -> dict:
    from domains.runs.services.run_reconciliation import reconcile_stale_runs
    from infrastructure.celery_async import run_async_task
    from infrastructure.neomodel_config import configure_neomodel

    configure_neomodel()

    async def _go() -> dict:
        return {"reconciled": await reconcile_stale_runs()}

    out = run_async_task(_go)
    if out.get("reconciled"):
        logger.info(f"run reconcile tick: {out}", extra={"tag": "reconcile"})
    return out
