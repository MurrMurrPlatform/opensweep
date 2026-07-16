"""Schema migration CLI.

Run inside the backend container (or any env with NEO4J_* configured):

    docker exec opensweep_backend python -m scripts.migrate status
    docker exec opensweep_backend python -m scripts.migrate up
    docker exec opensweep_backend python -m scripts.migrate down --to 3

`up` is what startup runs automatically; `down --to N` is the manual
pre-step when rolling a deployment back with OPENSWEEP_MIGRATIONS_AUTO_ROLLBACK
off (with it on — the default — the older image reverts by itself on boot).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


async def _connect() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from neomodel import adb
    from neomodel import config as neomodel_conf

    from infrastructure.neomodel_config import configure_neomodel

    configure_neomodel()
    await adb.set_connection(url=neomodel_conf.DATABASE_URL)
    await adb.cypher_query("RETURN 1")


async def _status() -> None:
    from infrastructure.migration_runner import build_plan, load_definitions, read_applied
    from migrations import migration_modules

    code = load_definitions(migration_modules())
    applied = await read_applied()
    applied_versions = {r.version for r in applied}
    print(f"code: {len(code)} migration(s), latest {max((d.version for d in code), default=0)}")
    print(f"database: {len(applied)} applied")
    for d in code:
        mark = "applied" if d.version in applied_versions else "PENDING"
        rev = "" if d.reversible else "  [irreversible]"
        print(f"  {d.version:>4}  {d.name:<40} {mark}{rev}")
    ahead = sorted(r.version for r in applied if r.version > len(code))
    if ahead:
        print(f"  database is AHEAD of code: {ahead} (deployment rollback pending)")


async def _up() -> None:
    from config import settings
    from infrastructure.migration_runner import migrate

    plan = await migrate(
        auto_rollback=settings.OPENSWEEP_MIGRATIONS_AUTO_ROLLBACK,
        lock_timeout_seconds=settings.OPENSWEEP_MIGRATIONS_LOCK_TIMEOUT_SECONDS,
    )
    print(
        f"reverted {[r.version for r in plan.to_revert]}, "
        f"applied {[m.version for m in plan.to_apply]}"
        if not plan.noop
        else "already up to date"
    )


async def _down(target: int) -> None:
    from infrastructure.migration_runner import downgrade_to

    reverted = await downgrade_to(target)
    print(f"reverted {reverted}" if reverted else f"nothing above version {target}")


async def main() -> None:
    parser = argparse.ArgumentParser(prog="scripts.migrate", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show code vs database migration state")
    sub.add_parser("up", help="apply pending migrations (same as startup)")
    down = sub.add_parser("down", help="revert applied migrations above --to")
    down.add_argument("--to", type=int, required=True, help="target version to end at")
    args = parser.parse_args()

    await _connect()
    if args.command == "status":
        await _status()
    elif args.command == "up":
        await _up()
    elif args.command == "down":
        await _down(args.to)


if __name__ == "__main__":
    asyncio.run(main())
