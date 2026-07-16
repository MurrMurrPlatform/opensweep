"""Destroy sandboxes whose `cleanup_after` has passed."""

from celery_app import app
from infrastructure.celery_async import run_async_task


@app.task(name="opensweep.execution.cleanup_sandboxes")
def cleanup_sandboxes_task() -> dict:
    from domains.execution.services.sandbox_service import SandboxService
    from infrastructure.neomodel_config import configure_neomodel

    configure_neomodel()
    count = run_async_task(SandboxService().cleanup_expired)
    return {"destroyed": count}
