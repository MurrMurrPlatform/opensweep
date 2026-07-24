"""The codex run/workflow path holds the subscription credential lease.

Runs launched from Ask / Area Map / actions go through the CLI tracking adapter,
which now wraps the whole run in `codex_credential.codex_credential_txn` — the
same exclusive per-credential lease + rotation write-back the interactive turn
path uses. Without it a run seeds the sealed auth.json, lets codex rotate the
refresh token, then discards it, so the next run reuses a consumed refresh token
and codex fails "access token could not be refreshed".

These tests cover the lease-contention edge the lease introduces: a second codex
run on the same subscription must PAUSE (resumable) rather than fail hard.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import HTTPException

from domains.executors import cli_tracking
from domains.executors.base import DispatchRequest
from domains.runs.schemas import RunStatus


def _req(**overrides):
    base = dict(
        run_uid="run-1",
        scheduled_agent_uid="agent-1",
        repository_uid="repo-1",
        repository_local_path=None,
        intent="ask",
    )
    base.update(overrides)
    return DispatchRequest(**base)


async def test_lease_busy_pauses_run_instead_of_failing(monkeypatch):
    provider = SimpleNamespace(uid="p1", kind="codex_subscription", model="")

    async def _resolve(*_a, **_k):
        return provider

    @asynccontextmanager
    async def _busy_txn(_provider):
        raise HTTPException(status_code=503, detail="codex subscription busy")
        yield  # pragma: no cover — unreachable, makes this an async CM

    monkeypatch.setattr(cli_tracking, "resolve_provider", _resolve)
    monkeypatch.setattr(cli_tracking.codex_credential, "codex_credential_txn", _busy_txn)

    result = await cli_tracking.CodexAdapter().dispatch(_req())

    # Resumable pause, not a hard failure — the resume beat re-dispatches it.
    assert result.status == RunStatus.PAUSED_QUOTA
    assert "busy" in (result.error or "").lower()


async def test_lease_available_runs_the_passes(monkeypatch):
    """When the lease is free, dispatch proceeds into the run passes (the txn is
    a no-op passthrough here) and returns whatever the passes produce."""
    provider = SimpleNamespace(uid="p1", kind="codex_subscription", model="")

    async def _resolve(*_a, **_k):
        return provider

    @asynccontextmanager
    async def _free_txn(_provider):
        yield

    sentinel = object()

    async def _run_passes(self, req, prov, started):
        assert prov is provider
        return sentinel

    monkeypatch.setattr(cli_tracking, "resolve_provider", _resolve)
    monkeypatch.setattr(cli_tracking.codex_credential, "codex_credential_txn", _free_txn)
    monkeypatch.setattr(cli_tracking._CLITrackingAdapter, "_run_passes", _run_passes)

    result = await cli_tracking.CodexAdapter().dispatch(_req())
    assert result is sentinel
