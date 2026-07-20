"""Celery beat tick — advance running audit campaigns (mark/dispatch/finalize)."""

from __future__ import annotations

from celery_app import app
from logging_config import logger


@app.task(name="opensweep.campaigns.tick")
def campaign_tick() -> dict:
    from domains.campaigns.services.tick import tick_campaigns
    from infrastructure.celery_async import run_async_task
    from infrastructure.neomodel_config import configure_neomodel

    configure_neomodel()

    async def _go():
        # run_async_task reconnected the async neomodel driver to this
        # task's fresh event loop (infrastructure/celery_async.py).
        return await tick_campaigns()

    out = run_async_task(_go)
    logger.info(f"campaign tick: {out}", extra={"tag": "campaigns"})
    return out
