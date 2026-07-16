"""Reseed OpenSweep data: wipe all LLM/derived state, keep configuration.

Thin CLI wrapper around `infrastructure.dev_reset.dev_reset()` — the same
canonical path the admin API (POST /api/v1/platform-config/dev-reset) uses,
so CLI and UI resets always wipe and seed identically. See that module for
the exact wipe/keep/seed lists.

Run inside the backend container:
    docker exec opensweep_backend python -m scripts.reseed

All LLM-derived state (findings, runs, docs, memories, checked stamps) is
gone afterwards; run a Sweep per repository to regenerate docs and audits.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


async def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from infrastructure.neomodel_config import configure_neomodel
    from neomodel import adb
    from neomodel import config as neomodel_conf

    configure_neomodel()
    if not adb.driver:
        await adb.set_connection(url=neomodel_conf.DATABASE_URL)

    from infrastructure.dev_reset import dev_reset

    result = await dev_reset()
    print(f"Deleted: {result['deleted']}")
    print(f"Seeded:  {result['seeded']}")
    print("LLM-derived state wiped. Run a Sweep per repository to regenerate docs and audits.")


if __name__ == "__main__":
    asyncio.run(main())
