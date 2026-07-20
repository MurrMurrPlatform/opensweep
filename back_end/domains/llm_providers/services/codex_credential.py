"""Per-subscription serialization + durable write-back for codex managed auth.

See docs/superpowers/specs/2026-07-20-codex-subscription-token-refresh-design.md.

Approach A: while a codex-subscription turn runs, hold an **exclusive
per-provider lease** so only one codex process ever touches that rotating
credential. Codex performs the OAuth refresh itself (proactively near expiry, or
reactively on a 401) with exclusive access; on turn exit OpenSweep persists
whatever codex left in `CODEX_HOME/auth.json` back into the sealed credential,
under a **compare-and-swap on `credential_revision`** so a credential the user
re-pasted mid-turn is never clobbered.

The lease is a Neo4j lock node (same mechanism as `infrastructure/seeding/lock.py`).
Coordination therefore lives in the **same durable store as the credential**: if
Neo4j is unreachable no turn runs at all, so there is no split-brain window and
no local-lock fallback to get wrong. A crashed holder's lease self-expires.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import HTTPException
from neomodel import adb

from domains.llm_providers.schemas import LLMProviderKind
from domains.llm_providers.services import codex_auth
from domains.llm_providers.services.credentials import sealed_secret
from domains.llm_providers.services.runtime_env import _codex_home
from infrastructure import secretbox
from logging_config import logger

# Lease is short and renewed while the turn runs (turns can last up to
# TURN_TIMEOUT_SECONDS = 3600). A dead holder's lease expires after the TTL.
_LEASE_TTL_SECONDS = 120
_RENEW_INTERVAL_SECONDS = 40
_ACQUIRE_POLL_SECONDS = 1.0


def _wait_timeout_seconds() -> int:
    """How long a queued turn waits for the subscription before returning a
    retryable error. Configurable; kept short so a request never blocks for a
    whole long-running turn."""
    try:
        return max(1, int(os.environ.get("OPENSWEEP_CODEX_LOCK_WAIT_SECONDS", "120")))
    except ValueError:
        return 120


def is_codex_managed(provider) -> bool:
    """True for a codex-subscription provider with a UI-stored auth.json (the
    only path that needs serialization + write-back). Bind-mount providers —
    no stored secret — are left untouched; codex owns the host ~/.codex."""
    return (
        provider is not None
        and (getattr(provider, "kind", "") or "") == LLMProviderKind.CODEX_SUBSCRIPTION.value
        and bool((getattr(provider, "credential_secret", "") or "").strip())
    )


# ── Neo4j per-provider lease ─────────────────────────────────────────────────


async def _try_acquire(uid: str, token: str) -> bool:
    rows, _ = await adb.cypher_query(
        """
        MERGE (l:CodexCredLock {id: $id})
        WITH l
        WHERE l.holder IS NULL OR l.expires_at IS NULL OR l.expires_at < timestamp()
        SET l.holder = $token, l.expires_at = timestamp() + $ttl_ms
        RETURN l.holder
        """,
        {"id": uid, "token": token, "ttl_ms": _LEASE_TTL_SECONDS * 1000},
    )
    return bool(rows) and rows[0][0] == token


async def _renew(uid: str, token: str) -> bool:
    rows, _ = await adb.cypher_query(
        """
        MATCH (l:CodexCredLock {id: $id})
        WHERE l.holder = $token
        SET l.expires_at = timestamp() + $ttl_ms
        RETURN l.holder
        """,
        {"id": uid, "token": token, "ttl_ms": _LEASE_TTL_SECONDS * 1000},
    )
    return bool(rows)


async def _release(uid: str, token: str) -> None:
    await adb.cypher_query(
        """
        MATCH (l:CodexCredLock {id: $id})
        WHERE l.holder = $token
        SET l.holder = NULL, l.expires_at = NULL
        """,
        {"id": uid, "token": token},
    )


async def _acquire_or_raise(uid: str, token: str) -> None:
    deadline = time.monotonic() + _wait_timeout_seconds()
    waited = False
    while not await _try_acquire(uid, token):
        if time.monotonic() >= deadline:
            raise HTTPException(
                status_code=503,
                detail="Another run is using this Codex subscription — retry shortly.",
            )
        waited = True
        # asyncio.sleep is cancellable, so a client that gives up while waiting
        # cancels cleanly.
        await asyncio.sleep(_ACQUIRE_POLL_SECONDS)
    if waited:
        logger.info(f"codex subscription {uid}: acquired after waiting", extra={"tag": "codex"})


async def _renew_loop(uid: str, token: str) -> None:
    while True:
        await asyncio.sleep(_RENEW_INTERVAL_SECONDS)
        try:
            if not await _renew(uid, token):
                # Lost the lease (expired + taken). Nothing safe to do but stop;
                # the write-back CAS is the real correctness backstop.
                logger.warning(
                    f"codex subscription {uid}: lease lost during turn", extra={"tag": "codex"}
                )
                return
        except Exception as exc:  # noqa: BLE001 — renewal is best-effort
            logger.warning(
                f"codex subscription {uid}: lease renewal failed: {exc}", extra={"tag": "codex"}
            )


# ── Durable write-back (compare-and-swap on credential_revision) ──────────────


async def _read_credential(uid: str) -> tuple[str, int]:
    rows, _ = await adb.cypher_query(
        "MATCH (p:LLMProvider {uid: $uid}) "
        "RETURN p.credential_secret, coalesce(p.credential_revision, 0)",
        {"uid": uid},
    )
    if not rows:
        return "", 0
    return (rows[0][0] or ""), int(rows[0][1] or 0)


async def _cas_persist(uid: str, sealed: str, expected_revision: int) -> bool:
    """Persist a rotated (sealed) auth.json only if the credential is still at
    the revision we seeded from. Returns False when a newer credential won —
    e.g. the user re-pasted, or a peer already persisted — in which case the
    stale write-back is dropped rather than clobbering the newer value."""
    rows, _ = await adb.cypher_query(
        """
        MATCH (p:LLMProvider {uid: $uid})
        WHERE coalesce(p.credential_revision, 0) = $rev
        SET p.credential_secret = $sealed,
            p.credential_revision = $rev + 1,
            p.needs_reauth = false,
            p.auth_state_uncertain = false
        RETURN p.credential_revision
        """,
        {"uid": uid, "sealed": sealed, "rev": expected_revision},
    )
    return bool(rows)


async def mark_needs_reauth(uid: str) -> None:
    """Flag the credential as permanently dead (refresh token revoked/rotated
    away). Set outside the CAS so it lands even if the revision moved."""
    await adb.cypher_query(
        "MATCH (p:LLMProvider {uid: $uid}) SET p.needs_reauth = true", {"uid": uid}
    )


async def _mark_uncertain(uid: str) -> None:
    await adb.cypher_query(
        "MATCH (p:LLMProvider {uid: $uid}) SET p.auth_state_uncertain = true", {"uid": uid}
    )


def _auth_json_path(provider) -> str:
    return os.path.join(_codex_home(provider), ".codex", "auth.json")


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


async def _write_back(provider, seed_plaintext: str, expected_revision: int) -> None:
    """Persist codex's post-turn auth.json if it rotated to a valid credential
    for the same account. Never raises — credential hygiene must not fail a run."""
    uid = provider.uid
    result_text = _read_text(_auth_json_path(provider))
    decision = codex_auth.decide_write_back(seed_plaintext, result_text)
    if decision == codex_auth.NOOP:
        return
    if decision == codex_auth.UNCERTAIN:
        await _mark_uncertain(uid)
        logger.warning(
            f"codex subscription {uid}: auth.json changed but is not valid — "
            f"state uncertain",
            extra={"tag": "codex"},
        )
        return
    if decision == codex_auth.REJECT_ACCOUNT:
        logger.warning(
            f"codex subscription {uid}: post-turn auth.json is a different account "
            f"— write-back rejected",
            extra={"tag": "codex"},
        )
        return
    # PERSIST — codex rotated the token; store it verbatim (lossless) under CAS.
    sealed = sealed_secret(result_text)  # type: ignore[arg-type]  (PERSIST ⇒ not None)
    if await _cas_persist(uid, sealed, expected_revision):
        logger.info(
            f"codex subscription {uid}: persisted rotated auth.json (rev "
            f"{expected_revision} → {expected_revision + 1})",
            extra={"tag": "codex"},
        )
    else:
        logger.info(
            f"codex subscription {uid}: rotated auth.json dropped — a newer "
            f"credential won the compare-and-swap",
            extra={"tag": "codex"},
        )


# ── Public transaction context manager ───────────────────────────────────────


@asynccontextmanager
async def codex_credential_txn(provider) -> AsyncIterator[None]:
    """Serialize a codex-subscription turn and durably persist any rotation.

    Inert for non-managed providers (bind-mount / non-codex): yields immediately
    with no lock and no write-back. For a managed provider it:

      1. acquires the exclusive per-subscription lease (503 if another run holds
         it past the wait budget),
      2. re-reads the credential under the lease and seeds it to the worker
         CODEX_HOME (establishing the write-back baseline even if codex never
         runs this turn), refreshing the in-memory node so downstream seeding
         uses the current revision,
      3. renews the lease while the turn runs,
      4. on exit — success, failure, cancellation, or timeout — reads back
         codex's auth.json and CAS-persists it if it rotated, then releases.
    """
    if not is_codex_managed(provider):
        yield
        return

    uid = provider.uid
    token = uuid4().hex
    await _acquire_or_raise(uid, token)
    renew_task = asyncio.create_task(_renew_loop(uid, token))
    try:
        # Latest credential wins — a peer may have rotated it since this request
        # loaded the node. Seed from that, and record the revision the CAS must
        # match at write-back.
        sealed_seed, expected_revision = await _read_credential(uid)
        if not sealed_seed:
            sealed_seed = provider.credential_secret or ""
        provider.credential_secret = sealed_seed
        provider.credential_revision = expected_revision
        seed_plaintext = secretbox.unseal(sealed_seed)
        _seed_baseline(provider, seed_plaintext)
        yield
    finally:
        renew_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await renew_task
        try:
            await _write_back(provider, seed_plaintext, expected_revision)
        except Exception as exc:  # noqa: BLE001 — write-back must never fail a run
            logger.warning(
                f"codex subscription {uid}: write-back failed: {exc}", extra={"tag": "codex"}
            )
        finally:
            with contextlib.suppress(Exception):
                await _release(uid, token)


def _seed_baseline(provider, seed_plaintext: str) -> None:
    """Write the current credential to the worker CODEX_HOME under the lease, so
    the post-turn diff has a correct baseline even if codex never runs (e.g. the
    turn fails during workspace prep). `codex_turn_env` re-writes the identical
    seed just before launch — harmless. Never raises."""
    path = _auth_json_path(provider)
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(seed_plaintext)
        os.chmod(path, 0o600)
    except OSError as exc:
        logger.warning(
            f"codex subscription {provider.uid}: could not seed baseline: {exc}",
            extra={"tag": "codex"},
        )
