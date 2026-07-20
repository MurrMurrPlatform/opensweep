"""Codex credential lease + durable write-back tests.

DB-free: neomodel/adb is monkeypatched with an in-memory fake that models the
CodexCredLock node semantics and the LLMProvider credential compare-and-swap.
"""

import json
import os
from types import SimpleNamespace

import pytest

from domains.llm_providers.services import codex_credential


def _auth(access="a1", refresh="r1", account="acct-1", last="t1"):
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "id_token": "i1",
                "access_token": access,
                "refresh_token": refresh,
                "account_id": account,
            },
            "last_refresh": last,
        }
    )


class _FakeAdb:
    """Models CodexCredLock (holder/expires_at with a controllable clock) and
    LLMProvider credential state (secret + revision + flags)."""

    def __init__(self):
        self.now_ms = 1_000_000
        self.locks: dict[str, dict] = {}
        self.providers: dict[str, dict] = {}

    async def cypher_query(self, query, params=None):
        params = params or {}
        q = " ".join(query.split())

        if q.startswith("MERGE (l:CodexCredLock"):
            lock = self.locks.setdefault(params["id"], {"holder": None, "expires_at": None})
            free = (
                lock["holder"] is None
                or lock["expires_at"] is None
                or lock["expires_at"] < self.now_ms
            )
            if free:
                lock["holder"] = params["token"]
                lock["expires_at"] = self.now_ms + params["ttl_ms"]
            return [[lock["holder"]]], None

        if q.startswith("MATCH (l:CodexCredLock") and "SET l.expires_at" in q:
            lock = self.locks.get(params["id"])
            if lock and lock["holder"] == params["token"]:
                lock["expires_at"] = self.now_ms + params["ttl_ms"]
                return [[lock["holder"]]], None
            return [], None

        if q.startswith("MATCH (l:CodexCredLock") and "SET l.holder = NULL" in q:
            lock = self.locks.get(params["id"])
            if lock and lock["holder"] == params["token"]:
                lock["holder"] = None
                lock["expires_at"] = None
            return [], None

        if "RETURN p.credential_secret" in q:
            p = self.providers.get(params["uid"], {})
            return [[p.get("credential_secret", ""), p.get("credential_revision", 0)]], None

        if "SET p.credential_secret" in q:  # CAS
            p = self.providers.get(params["uid"])
            if p is not None and p.get("credential_revision", 0) == params["rev"]:
                p["credential_secret"] = params["sealed"]
                p["credential_revision"] = params["rev"] + 1
                p["needs_reauth"] = False
                p["auth_state_uncertain"] = False
                return [[p["credential_revision"]]], None
            return [], None

        if "SET p.needs_reauth = true" in q:
            self.providers.setdefault(params["uid"], {})["needs_reauth"] = True
            return [], None

        if "SET p.auth_state_uncertain = true" in q:
            self.providers.setdefault(params["uid"], {})["auth_state_uncertain"] = True
            return [], None

        raise AssertionError(f"unhandled query: {q}")


@pytest.fixture
def fake(monkeypatch, tmp_path):
    adb = _FakeAdb()
    monkeypatch.setattr(codex_credential, "adb", adb)
    # Point the worker CODEX_HOME at a temp dir instead of the real /tmp.
    home = str(tmp_path / "codex-home")
    monkeypatch.setattr(codex_credential, "_codex_home", lambda provider: home)
    adb._home = home  # convenience for tests
    return adb


def _provider(secret):
    return SimpleNamespace(uid="p1", kind="codex_subscription", credential_secret=secret)


def _auth_path(home):
    return os.path.join(home, ".codex", "auth.json")


def _write_disk(home, text):
    path = _auth_path(home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ── is_codex_managed ─────────────────────────────────────────────────────────


def test_is_codex_managed():
    assert codex_credential.is_codex_managed(_provider(_auth())) is True
    assert codex_credential.is_codex_managed(_provider("")) is False
    assert codex_credential.is_codex_managed(None) is False
    assert (
        codex_credential.is_codex_managed(
            SimpleNamespace(uid="x", kind="openai_api", credential_secret="sk-1")
        )
        is False
    )


async def test_inert_txn_for_unmanaged_provider(fake):
    async with codex_credential.codex_credential_txn(_provider("")):
        pass
    # No lock taken, no provider row touched.
    assert fake.locks == {}


# ── lease mutual exclusion + expiry ──────────────────────────────────────────


async def test_lease_is_exclusive_until_released(fake):
    assert await codex_credential._try_acquire("p1", "tokA") is True
    assert await codex_credential._try_acquire("p1", "tokB") is False
    await codex_credential._release("p1", "tokA")
    assert await codex_credential._try_acquire("p1", "tokB") is True


async def test_lease_self_expires_for_dead_holder(fake):
    assert await codex_credential._try_acquire("p1", "tokA") is True
    assert await codex_credential._try_acquire("p1", "tokB") is False
    fake.now_ms += codex_credential._LEASE_TTL_SECONDS * 1000 + 1
    # Holder A "died"; its lease lapsed, so B can take it.
    assert await codex_credential._try_acquire("p1", "tokB") is True


async def test_acquire_or_raise_503_when_held(fake, monkeypatch):
    monkeypatch.setenv("OPENSWEEP_CODEX_LOCK_WAIT_SECONDS", "1")
    monkeypatch.setattr(codex_credential, "_ACQUIRE_POLL_SECONDS", 0.01)
    await codex_credential._try_acquire("p1", "holder")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        await codex_credential._acquire_or_raise("p1", "loser")
    assert ei.value.status_code == 503


# ── write-back transaction ───────────────────────────────────────────────────


async def test_txn_persists_codex_rotation(fake):
    seed = _auth(access="a1", refresh="r1", last="t1")
    fake.providers["p1"] = {"credential_secret": seed, "credential_revision": 0}
    provider = _provider(seed)

    async with codex_credential.codex_credential_txn(provider):
        # Simulate codex rotating the token mid-turn.
        _write_disk(fake._home, _auth(access="a2", refresh="r2", last="t2"))

    p = fake.providers["p1"]
    assert p["credential_revision"] == 1
    assert json.loads(p["credential_secret"])["tokens"]["access_token"] == "a2"
    assert p["needs_reauth"] is False
    # Lock released.
    assert fake.locks["p1"]["holder"] is None


async def test_txn_noop_when_codex_does_not_rotate(fake):
    seed = _auth()
    fake.providers["p1"] = {"credential_secret": seed, "credential_revision": 0}
    provider = _provider(seed)

    async with codex_credential.codex_credential_txn(provider):
        pass  # codex left the seeded baseline untouched

    assert fake.providers["p1"]["credential_revision"] == 0


async def test_txn_writeback_loses_cas_to_concurrent_resave(fake):
    seed = _auth(access="a1")
    fake.providers["p1"] = {"credential_secret": seed, "credential_revision": 0}
    provider = _provider(seed)

    async with codex_credential.codex_credential_txn(provider):
        _write_disk(fake._home, _auth(access="a2"))  # codex rotated
        # Meanwhile the user re-pastes a fresh credential: revision bumps.
        fake.providers["p1"]["credential_secret"] = _auth(access="USER_NEW")
        fake.providers["p1"]["credential_revision"] = 7

    p = fake.providers["p1"]
    # The stale write-back (expected rev 0) lost the CAS — user's value stands.
    assert p["credential_revision"] == 7
    assert json.loads(p["credential_secret"])["tokens"]["access_token"] == "USER_NEW"


async def test_txn_rejects_account_swap(fake):
    seed = _auth(account="acct-1", access="a1")
    fake.providers["p1"] = {"credential_secret": seed, "credential_revision": 0}
    provider = _provider(seed)

    async with codex_credential.codex_credential_txn(provider):
        _write_disk(fake._home, _auth(account="acct-2", access="a2"))

    assert fake.providers["p1"]["credential_revision"] == 0  # not persisted


async def test_txn_marks_uncertain_on_partial_file(fake):
    seed = _auth()
    fake.providers["p1"] = {"credential_secret": seed, "credential_revision": 0}
    provider = _provider(seed)

    async with codex_credential.codex_credential_txn(provider):
        _write_disk(fake._home, '{"tokens": {"access_token": ')  # truncated

    p = fake.providers["p1"]
    assert p["credential_revision"] == 0
    assert p.get("auth_state_uncertain") is True


async def test_mark_needs_reauth(fake):
    fake.providers["p1"] = {"credential_secret": _auth(), "credential_revision": 0}
    await codex_credential.mark_needs_reauth("p1")
    assert fake.providers["p1"]["needs_reauth"] is True
