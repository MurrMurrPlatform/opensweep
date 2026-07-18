"""Thread hooks are no-ops for standalone runs and never raise."""

import asyncio
from types import SimpleNamespace

from domains.threads.services.hooks import note_pr_opened_for_run


def test_noop_for_run_without_thread():
    run = SimpleNamespace(thread_uid="", linked_pr_uid="pr-1")
    # Must complete without touching the DB (no Thread lookup for "").
    asyncio.run(note_pr_opened_for_run(run))


def test_never_raises_on_lookup_failure(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("db down")

    import domains.threads.services.hooks as hooks

    monkeypatch.setattr(hooks, "_advance_to_in_review", boom)
    run = SimpleNamespace(uid="r-1", thread_uid="th-1", linked_pr_uid="pr-1")
    asyncio.run(note_pr_opened_for_run(run))  # no raise
