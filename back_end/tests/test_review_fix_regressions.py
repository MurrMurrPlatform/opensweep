"""Regression pins for the self-review findings.

B1: neomodel save() writes EVERY property, so record_event MUST reload
    before appending — a stale save reverted phase transitions (reproduced
    live: start_implement left threads in 'refining' forever).
S1: refresh-token reuse must revoke the whole rotated family.
B2: platform-authored messages are pre-checked against run status so they
    are never fired-and-lost at a mid-turn run.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import domains.threads.services.thread_service as ts


class _FakeThread:
    def __init__(self, uid, phase, events=None):
        self.uid = uid
        self.phase = phase
        self.events = list(events or [])
        self.updated_at = None
        self.saved = 0

    async def save(self):
        self.saved += 1


def test_record_event_appends_to_fresh_node_not_stale(monkeypatch):
    # The stale caller object believes phase == "refining"; the DB (fresh
    # node) has moved on to "implementing". The append must land on — and
    # save — the FRESH node, never the stale one.
    stale = _FakeThread("th-1", "refining")
    fresh = _FakeThread("th-1", "implementing", events=[{"type": "phase_changed"}])

    class _Nodes:
        async def get_or_none(self, **kw):
            return fresh

    monkeypatch.setattr(ts, "Thread", SimpleNamespace(nodes=_Nodes()))
    asyncio.run(ts.ThreadService().record_event(stale, "pr_opened", pr_uid="pr-1"))

    assert fresh.saved == 1
    assert stale.saved == 0  # a stale save would have clobbered phase
    assert fresh.events[-1]["type"] == "pr_opened"
    # Caller's view refreshed so subsequent reads see reality.
    assert stale.phase == "implementing"
    assert stale.events[-1]["type"] == "pr_opened"


def test_refresh_reuse_revokes_the_whole_family(monkeypatch):
    from domains.oauth_mcp.services import oauth_service

    now = datetime.now(UTC)

    def _tok(uid, revoked, rotated_to=""):
        t = SimpleNamespace(
            uid=uid,
            client_id="c-1",
            user_uid="u-1",
            revoked_at=now if revoked else None,
            rotated_to=rotated_to,
            refresh_expires_at=now + timedelta(days=1),
        )

        async def save():
            t.saved = True

        t.save = save
        return t

    # stolen (already rotated) -> successor -> live grandchild
    grandchild = _tok("t-3", revoked=False)
    child = _tok("t-2", revoked=False, rotated_to="t-3")
    stolen = _tok("t-1", revoked=True, rotated_to="t-2")
    by_uid = {t.uid: t for t in (stolen, child, grandchild)}

    class _Nodes:
        async def get_or_none(self, **kw):
            if "uid" in kw:
                return by_uid.get(kw["uid"])
            return stolen  # refresh_hash lookup

    monkeypatch.setattr(oauth_service, "OAuthToken", SimpleNamespace(nodes=_Nodes()))

    async def _no_audit(**kw):
        return None

    monkeypatch.setattr(oauth_service, "write_audit", _no_audit)

    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        asyncio.run(oauth_service.refresh_tokens(refresh_token="osmcr_x", client_id="c-1"))
    # The attacker's live successors are dead.
    assert child.revoked_at is not None
    assert grandchild.revoked_at is not None


def test_run_accepts_message_gates_on_status(monkeypatch):
    import domains.investigations.models as run_models
    from domains.threads.services import thread_run

    def _with_run(status):
        run = SimpleNamespace(status=status, playbook="thread")

        class _Nodes:
            async def get_or_none(self, **kw):
                return run

        monkeypatch.setattr(run_models, "Run", SimpleNamespace(nodes=_Nodes()))

    _with_run("running")
    assert asyncio.run(thread_run.run_accepts_message("r-1")) is False
    _with_run("queued")
    assert asyncio.run(thread_run.run_accepts_message("r-1")) is False
    _with_run("awaiting_input")
    assert asyncio.run(thread_run.run_accepts_message("r-1")) is True
    _with_run("failed")  # recovery loop accepts follow-ups
    assert asyncio.run(thread_run.run_accepts_message("r-1")) is True
