"""Per-event-loop async Redis client.

All OpenSweep keys MUST be namespaced under `opensweep:` — db 0 is shared with the
Celery broker/result backend, so an un-prefixed key risks colliding with
Celery's own structures.

No availability cooldown lives here — callers own their fallback policy
(degrade gracefully, retry, or fail loudly as appropriate for the call site).
"""

from __future__ import annotations

import asyncio
from typing import Any

import redis.asyncio as aioredis

from redis_config import get_redis_url

# A redis.asyncio.Redis binds its connections to the loop it is first used
# on; Celery tasks each run in fresh asyncio.run() loops, so a client bound
# to a closed loop must never be reused. Keep one client per loop (strong
# loop ref so an id() is never reused while cached — mirrors
# infrastructure/github_app._locks_by_loop).
_clients_by_loop: dict[int, tuple[Any, aioredis.Redis]] = {}


def get_async_redis() -> aioredis.Redis:
    """The async Redis client for the CURRENT event loop (db 0)."""
    loop = asyncio.get_running_loop()
    entry = _clients_by_loop.get(id(loop))
    if entry is not None and entry[0] is loop:
        return entry[1]
    for key in [k for k, (cached, _) in _clients_by_loop.items() if cached.is_closed()]:
        _clients_by_loop.pop(key, None)
    client = aioredis.Redis.from_url(
        get_redis_url(db=0),
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=2.0,
    )
    _clients_by_loop[id(loop)] = (loop, client)
    return client
