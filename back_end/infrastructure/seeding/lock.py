"""Lease lock for the seed pass.

Startup seeders look up rows by non-unique keys (RunPolicy.name,
AgentPrompt.source_url) and create them when absent — so two backend replicas
booting at once, or a backend boot racing the migration_tool, could both
decide a row is missing and create a duplicate. This is the same hazard the
migration runner guards with its :SchemaMigrationLock; seeding gets its own
lease node so a crashed holder can't wedge future boots.

Separate node from the migration lock on purpose: seeding runs AFTER
migrations release theirs, and a dev running the migration_tool against a live
backend should serialize with that backend's seed pass, not its migrations.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from neomodel import adb

from logging_config import logger

LOCK_TTL_SECONDS = 300  # lease length; re-acquired per pass, expires if the holder dies


class SeedLockTimeout(Exception):
    """Could not acquire the seed lock within the caller's budget."""


async def _try_acquire(token: str) -> bool:
    rows, _ = await adb.cypher_query(
        """
        MERGE (l:SeedLock {id: 'lock'})
        WITH l
        WHERE l.holder IS NULL OR l.expires_at IS NULL OR l.expires_at < timestamp()
        SET l.holder = $token, l.expires_at = timestamp() + $ttl_ms
        RETURN l.holder
        """,
        {"token": token, "ttl_ms": LOCK_TTL_SECONDS * 1000},
    )
    return bool(rows) and rows[0][0] == token


async def _release(token: str) -> None:
    await adb.cypher_query(
        """
        MATCH (l:SeedLock {id: 'lock'})
        WHERE l.holder = $token
        SET l.holder = NULL, l.expires_at = NULL
        """,
        {"token": token},
    )


@asynccontextmanager
async def seed_lock(*, timeout_seconds: int = 120):
    """Serialize the seed pass. Raises SeedLockTimeout if another holder keeps
    the lease past the timeout (the lease self-expires after LOCK_TTL_SECONDS,
    so a dead holder is never permanent)."""
    token = uuid4().hex
    deadline = time.monotonic() + timeout_seconds
    while not await _try_acquire(token):
        if time.monotonic() >= deadline:
            raise SeedLockTimeout(
                f"could not acquire the seed lock within {timeout_seconds}s — "
                f"another process is seeding (or died holding the lease; it "
                f"expires after {LOCK_TTL_SECONDS}s)"
            )
        await asyncio.sleep(1)
    try:
        yield
    finally:
        try:
            await _release(token)
        except Exception as exc:  # noqa: BLE001 — releasing best-effort; lease expires anyway
            logger.warning(f"seed lock release failed (lease will expire): {exc}", extra={"tag": "seeding"})
