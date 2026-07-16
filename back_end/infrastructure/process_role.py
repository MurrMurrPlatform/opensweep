"""Which process is this — the FastAPI backend or a Celery worker?

Run dispatch is an in-process asyncio task (lifecycle.trigger_run for API
dispatches, schedule_tick/resume_run for worker dispatches), so a Run row is
owned by the process that dispatched it and dies with that process. Runs are
stamped with usage["dispatch_runtime"] = get_role() at dispatch time, and each
role fails its own orphans at startup (app.py lifespan for the backend,
celery_app worker_ready for the worker).
"""

from __future__ import annotations

BACKEND = "backend"
WORKER = "worker"

_role = BACKEND


def set_role(role: str) -> None:
    global _role
    _role = role


def get_role() -> str:
    return _role
