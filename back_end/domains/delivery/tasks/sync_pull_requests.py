"""Celery beat tick — 2-way PR reconcile for every connected repository.

Webhooks keep the queue current in realtime; this sweep is the correctness
backstop that also imports PRs opened outside OpenSweep (no webhook configured,
missed delivery, or activity predating the installation). Deterministic and
LLM-free, so it is safe to run unconditionally.
"""

from __future__ import annotations

from celery_app import app
from logging_config import logger


@app.task(name="opensweep.delivery.sync_pull_requests")
def sync_pull_requests() -> dict:
    from domains.delivery.services.pull_request_service import PullRequestService
    from domains.repositories.models import Repository
    from infrastructure.celery_async import run_async_task
    from infrastructure.neomodel_config import configure_neomodel

    configure_neomodel()

    async def _go() -> dict:
        service = PullRequestService()
        repos = await Repository.nodes.filter(is_active=True)
        swept = synced = closed = errors = 0
        for repo in repos:
            if not (repo.github_owner and repo.github_repo):
                continue
            swept += 1
            try:
                result = await service.sync_repository(repo.uid)
                synced += result["synced"]
                closed += result["closed"]
            except Exception as exc:  # noqa: BLE001 — one repo must not break the sweep
                errors += 1
                logger.warning(
                    f"PR sweep failed for repository {repo.uid}: "
                    f"{type(exc).__name__}: {exc}",
                    extra={"tag": "delivery"},
                )
        return {"repositories": swept, "synced": synced, "closed": closed, "errors": errors}

    out = run_async_task(_go)
    logger.info(f"pull-request sweep: {out}", extra={"tag": "delivery"})
    return out
