"""Redis-backed single-use state nonces for the GitHub App OAuth-ish flows.

Multi-replica safe: every API replica shares one Redis, so a state minted by
replica A is consumable exactly once even when GitHub's redirect lands on
replica B. Keys hold the sha256 of the full signed token — the raw state
(which travels in URLs → browser history / Referer / proxy logs) is never
stored.

Redis errors propagate to the caller — callers own the fallback policy
(api/v1/github_app.py degrades to its file ledger).
"""

from __future__ import annotations

import hashlib

# Module-attribute access (not a from-import) so tests can monkeypatch
# infrastructure.redis_client.get_async_redis in one place.
from infrastructure import redis_client

_KEY_PREFIX = "opensweep:ghapp:state:"


def _key(state: str) -> str:
    return _KEY_PREFIX + hashlib.sha256(state.encode()).hexdigest()[:32]


async def remember_state_nonce(state: str, ttl_seconds: int) -> None:
    """Record a freshly minted state; expires with the state's own window."""
    await redis_client.get_async_redis().set(_key(state), "1", ex=ttl_seconds, nx=True)


async def consume_state_nonce(state: str) -> bool:
    """True exactly once per remembered state — DEL is the atomic check."""
    return int(await redis_client.get_async_redis().delete(_key(state))) == 1
