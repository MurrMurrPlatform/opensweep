"""Self-healing thread resolution (observed failure: the agent passed the
TICKET uid as thread_uid — both opaque hex — got a 404, and dumped the plan
into the ticket description as a fallback)."""

import asyncio
from types import SimpleNamespace

import domains.threads.services.thread_service as ts


class _Nodes:
    def __init__(self, by_uid=None, by_ticket=None):
        self._by_uid = by_uid or {}
        self._by_ticket = by_ticket or []

    async def get_or_none(self, **kw):
        return self._by_uid.get(kw.get("uid"))

    async def filter(self, **kw):
        return self._by_ticket


def _with_fakes(monkeypatch, *, threads_nodes, run=None):
    monkeypatch.setattr(ts, "Thread", SimpleNamespace(nodes=threads_nodes))
    import domains.investigations.models as run_models

    class _RunNodes:
        async def get_or_none(self, **kw):
            return run

    monkeypatch.setattr(run_models, "Run", SimpleNamespace(nodes=_RunNodes()))


def test_exact_thread_uid_wins(monkeypatch):
    thread = SimpleNamespace(uid="th-1", phase="refining")
    _with_fakes(monkeypatch, threads_nodes=_Nodes(by_uid={"th-1": thread}))
    assert asyncio.run(ts.resolve_thread("th-1")) is thread


def test_falls_back_to_calling_runs_thread(monkeypatch):
    thread = SimpleNamespace(uid="th-1", phase="refining")
    run = SimpleNamespace(thread_uid="th-1")
    _with_fakes(
        monkeypatch,
        threads_nodes=_Nodes(by_uid={"th-1": thread}),
        run=run,
    )
    # Wrong candidate (e.g. the ticket uid) + a run that knows its thread.
    assert asyncio.run(ts.resolve_thread("totally-wrong", run_uid="r-1")) is thread


def test_falls_back_to_active_thread_of_ticket(monkeypatch):
    done = SimpleNamespace(uid="th-0", phase="done")
    active = SimpleNamespace(uid="th-1", phase="refining")
    _with_fakes(monkeypatch, threads_nodes=_Nodes(by_ticket=[done, active]))
    assert asyncio.run(ts.resolve_thread("ticket-uid")) is active


def test_unresolvable_returns_none(monkeypatch):
    _with_fakes(monkeypatch, threads_nodes=_Nodes())
    assert asyncio.run(ts.resolve_thread("nope")) is None
    assert "ticket uid also works" in ts.THREAD_NOT_FOUND_DETAIL
