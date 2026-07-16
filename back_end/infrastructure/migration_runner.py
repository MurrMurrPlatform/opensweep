"""Versioned Neo4j migration runner (migrations/ package).

Production contract:

- **Atomic apply.** A migration's data statements run in ONE transaction
  together with its `SchemaMigration` bookkeeping node — if any statement
  fails, the transaction rolls back and the version marker is never
  written. The database is either at version N or version N+1, never
  in between. (Schema statements — CREATE/DROP CONSTRAINT|INDEX — cannot
  join a data transaction in Neo4j; they run auto-commit first and must be
  idempotent, so a crash between them and the data tx is repaired by the
  next boot re-running them.)

- **Deployment rollback (Coolify).** Each applied migration stores its
  DOWN statements in the database. When an older image boots against a
  database that is AHEAD of its code (the previous deployment applied
  migrations this image doesn't ship), the runner reverts those newer
  migrations using the STORED statements — no code from the newer image
  needed. Gated by OPENSWEEP_MIGRATIONS_AUTO_ROLLBACK; a migration applied
  with an empty DOWN is irreversible and fails the boot instead, with
  instructions.

- **Startup is fail-hard.** A migration error must abort the boot so the
  platform (Coolify healthcheck) keeps/returns to the previous deployment
  instead of serving a half-migrated graph.

- **Single runner.** A lease-style lock node serializes concurrent boots
  (backend replicas, backend + tooling). The lease expires so a crashed
  holder never wedges deploys.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from types import ModuleType
from uuid import uuid4

from neomodel import adb

from logging_config import logger

LOCK_TTL_SECONDS = 900  # lease length; re-acquired per boot, expires if the holder dies


class MigrationError(Exception):
    """Any condition that must abort startup: failed statement, checksum
    drift, non-contiguous versions, irreversible auto-rollback, lock
    timeout."""


@dataclass(frozen=True)
class MigrationDef:
    """A migration as shipped in code (migrations/m*.py)."""

    version: int
    name: str
    schema_up: tuple[str, ...] = ()
    schema_down: tuple[str, ...] = ()
    up: tuple[str, ...] = ()
    down: tuple[str, ...] = ()

    @property
    def checksum(self) -> str:
        payload = "\n".join(
            [
                f"v{self.version}:{self.name}",
                *self.schema_up,
                "--",
                *self.schema_down,
                "--",
                *self.up,
                "--",
                *self.down,
            ]
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @property
    def reversible(self) -> bool:
        """A migration that changes something must say how to undo it."""
        did_something = bool(self.up or self.schema_up)
        can_undo = bool(self.down or self.schema_down)
        return can_undo or not did_something


@dataclass(frozen=True)
class AppliedRecord:
    """A migration as recorded in the database when it was applied."""

    version: int
    name: str
    checksum: str
    down: tuple[str, ...] = ()
    schema_down: tuple[str, ...] = ()
    reversible: bool = True


@dataclass
class Plan:
    """What migrate() will do, computed before touching anything."""

    to_revert: list[AppliedRecord] = field(default_factory=list)  # newest first
    to_apply: list[MigrationDef] = field(default_factory=list)  # oldest first

    @property
    def noop(self) -> bool:
        return not self.to_revert and not self.to_apply


# ── Pure planning (unit-tested without a database) ──────────────────────────


def load_definitions(modules: list[ModuleType]) -> list[MigrationDef]:
    defs = [
        MigrationDef(
            version=int(m.VERSION),
            name=str(m.NAME),
            schema_up=tuple(getattr(m, "SCHEMA_UP", []) or []),
            schema_down=tuple(getattr(m, "SCHEMA_DOWN", []) or []),
            up=tuple(getattr(m, "UP", []) or []),
            down=tuple(getattr(m, "DOWN", []) or []),
        )
        for m in modules
    ]
    defs.sort(key=lambda d: d.version)
    expected = list(range(1, len(defs) + 1))
    if [d.version for d in defs] != expected:
        raise MigrationError(
            f"migration versions must be contiguous from 1; found "
            f"{[d.version for d in defs]} — renumber after resolving the merge"
        )
    for d in defs:
        if not d.reversible:
            logger.warning(
                f"migration {d.version} ({d.name}) has no DOWN — deployment "
                f"rollback past it will require manual intervention",
                extra={"tag": "migrations"},
            )
    return defs


def build_plan(code: list[MigrationDef], applied: list[AppliedRecord]) -> Plan:
    """Diff code migrations against the database's applied set.

    - checksum drift on a shared version → error (someone edited an applied
      migration file instead of adding a new one)
    - database ahead of code → those versions go to `to_revert` (the
      Coolify-rollback case)
    - code ahead of database → those versions go to `to_apply`
    """
    by_version = {d.version: d for d in code}
    code_max = max((d.version for d in code), default=0)
    plan = Plan()
    for rec in sorted(applied, key=lambda r: r.version):
        known = by_version.get(rec.version)
        if known is None and rec.version <= code_max:
            raise MigrationError(
                f"database has migration {rec.version} ({rec.name}) but the "
                f"code ships a different set below its max ({code_max}) — "
                f"the migration history has diverged; restore the matching "
                f"image or repair SchemaMigration nodes manually"
            )
        if known is not None and known.checksum != rec.checksum:
            raise MigrationError(
                f"migration {rec.version} ({rec.name}) was edited after being "
                f"applied (checksum mismatch). Applied migrations are "
                f"immutable — add a new migration instead"
            )
        if rec.version > code_max:
            plan.to_revert.append(rec)
    plan.to_revert.sort(key=lambda r: r.version, reverse=True)
    applied_versions = {r.version for r in applied}
    plan.to_apply = [d for d in code if d.version not in applied_versions]
    return plan


# ── Database side ────────────────────────────────────────────────────────────


async def read_applied() -> list[AppliedRecord]:
    rows, _ = await adb.cypher_query(
        """
        MATCH (m:SchemaMigration)
        RETURN m.version, m.name, m.checksum, m.down, m.schema_down, m.reversible
        ORDER BY m.version
        """
    )
    return [
        AppliedRecord(
            version=int(r[0]),
            name=str(r[1] or ""),
            checksum=str(r[2] or ""),
            down=tuple(r[3] or []),
            schema_down=tuple(r[4] or []),
            reversible=bool(r[5]) if r[5] is not None else True,
        )
        for r in rows
    ]


async def _apply(mig: MigrationDef) -> None:
    logger.info(f"migrations: applying {mig.version} ({mig.name})", extra={"tag": "migrations"})
    for stmt in mig.schema_up:  # auto-commit; idempotent by contract
        await adb.cypher_query(stmt)
    async with adb.transaction:
        for stmt in mig.up:
            await adb.cypher_query(stmt)
        # Bookkeeping joins the same transaction: version marker and data
        # changes commit or roll back together.
        await adb.cypher_query(
            """
            CREATE (m:SchemaMigration {
                version: $version, name: $name, checksum: $checksum,
                down: $down, schema_down: $schema_down,
                reversible: $reversible, applied_at: timestamp()
            })
            """,
            {
                "version": mig.version,
                "name": mig.name,
                "checksum": mig.checksum,
                "down": list(mig.down),
                "schema_down": list(mig.schema_down),
                "reversible": mig.reversible,
            },
        )


async def _revert(rec: AppliedRecord) -> None:
    """Revert using the statements STORED when the migration was applied —
    the running (older) image does not ship this migration's code."""
    if not rec.reversible:
        raise MigrationError(
            f"database is at migration {rec.version} ({rec.name}), which was "
            f"applied without a DOWN. Automatic rollback is impossible — "
            f"either redeploy the newer image, or repair the data manually "
            f"and delete its SchemaMigration node"
        )
    logger.warning(
        f"migrations: reverting {rec.version} ({rec.name}) — database is ahead of this build",
        extra={"tag": "migrations"},
    )
    async with adb.transaction:
        for stmt in rec.down:
            await adb.cypher_query(stmt)
        await adb.cypher_query(
            "MATCH (m:SchemaMigration {version: $version}) DELETE m",
            {"version": rec.version},
        )
    for stmt in rec.schema_down:  # auto-commit; idempotent by contract
        await adb.cypher_query(stmt)


# ── Lock ─────────────────────────────────────────────────────────────────────


async def _try_acquire_lock(token: str) -> bool:
    rows, _ = await adb.cypher_query(
        """
        MERGE (l:SchemaMigrationLock {id: 'lock'})
        WITH l
        WHERE l.holder IS NULL OR l.expires_at IS NULL OR l.expires_at < timestamp()
        SET l.holder = $token, l.expires_at = timestamp() + $ttl_ms
        RETURN l.holder
        """,
        {"token": token, "ttl_ms": LOCK_TTL_SECONDS * 1000},
    )
    return bool(rows) and rows[0][0] == token


async def _release_lock(token: str) -> None:
    await adb.cypher_query(
        """
        MATCH (l:SchemaMigrationLock {id: 'lock'})
        WHERE l.holder = $token
        SET l.holder = NULL, l.expires_at = NULL
        """,
        {"token": token},
    )


# ── Entry points ─────────────────────────────────────────────────────────────


async def migrate(*, auto_rollback: bool, lock_timeout_seconds: int = 180) -> Plan:
    """Bring the database to this build's migration version. Startup entry
    point — raises MigrationError (aborting the boot) on any failure."""
    from migrations import migration_modules

    code = load_definitions(migration_modules())
    token = uuid4().hex
    deadline = time.monotonic() + lock_timeout_seconds
    while not await _try_acquire_lock(token):
        if time.monotonic() >= deadline:
            raise MigrationError(
                f"could not acquire the migration lock within {lock_timeout_seconds}s — "
                f"another process is migrating (or died holding the lease; it "
                f"expires after {LOCK_TTL_SECONDS}s)"
            )
        await asyncio.sleep(2)

    try:
        plan = build_plan(code, await read_applied())
        if plan.noop:
            logger.info(
                f"migrations: up to date at version {max((d.version for d in code), default=0)}",
                extra={"tag": "migrations"},
            )
            return plan
        if plan.to_revert and not auto_rollback:
            versions = [r.version for r in plan.to_revert]
            raise MigrationError(
                f"database is ahead of this build (migrations {versions} not in "
                f"code) and OPENSWEEP_MIGRATIONS_AUTO_ROLLBACK is off. Redeploy the "
                f"newer image, or run `python -m scripts.migrate down --to "
                f"{min(versions) - 1}` from it first"
            )
        for rec in plan.to_revert:
            await _revert(rec)
        for mig in plan.to_apply:
            await _apply(mig)
        logger.info(
            f"migrations: done — reverted {len(plan.to_revert)}, applied {len(plan.to_apply)}",
            extra={"tag": "migrations"},
        )
        return plan
    finally:
        await _release_lock(token)


async def downgrade_to(target_version: int, *, lock_timeout_seconds: int = 60) -> list[int]:
    """Revert applied migrations above target_version (CLI / pre-rollback
    step). Uses the stored DOWN statements, newest first."""
    token = uuid4().hex
    deadline = time.monotonic() + lock_timeout_seconds
    while not await _try_acquire_lock(token):
        if time.monotonic() >= deadline:
            raise MigrationError("could not acquire the migration lock")
        await asyncio.sleep(2)
    try:
        applied = await read_applied()
        above = sorted(
            (r for r in applied if r.version > target_version),
            key=lambda r: r.version,
            reverse=True,
        )
        for rec in above:
            await _revert(rec)
        return [r.version for r in above]
    finally:
        await _release_lock(token)
