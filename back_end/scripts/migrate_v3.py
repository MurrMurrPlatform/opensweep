"""One-time V3 migration (PLATFORM_V3_DESIGN.md §11). Run once, no compat code.

- Relabel InvestigationRun → Run, map status completed → awaiting_input →
  ended (old runs are closed conversations), stamp playbook + linked uids
  from the parent Investigation's job_type/target. This keeps
  Finding.source_run_uid / Verdict.run_uid / FindingResolution provenance
  resolvable.
- Delete Session, Execution, and ExecutionEnvironment nodes (V3 §1). Session
  transcript files stay on disk, ignored.

Usage:  .venv/bin/python -m scripts.migrate_v3
"""

from __future__ import annotations

import asyncio

from neomodel import adb

from infrastructure.neomodel_config import configure_neomodel

_STATEMENTS = [
    # Relabel + field mapping. Old runs are finished conversations → ended.
    """
    MATCH (r:InvestigationRun)
    SET r:Run
    REMOVE r:InvestigationRun
    """,
    """
    MATCH (r:Run)
    WHERE r.status = 'completed'
    SET r.status = 'ended', r.ended_at = coalesce(r.completed_at, r.updated_at)
    """,
    # Playbook from the parent Investigation's job_type (default ask).
    """
    MATCH (r:Run)
    WHERE r.playbook IS NULL
    OPTIONAL MATCH (i:Investigation {uid: r.investigation_uid})
    SET r.playbook = CASE
        WHEN i IS NOT NULL AND i.job_type = 'implement' THEN 'implement'
        ELSE 'ask'
    END,
    r.title = coalesce(r.title, CASE WHEN i IS NOT NULL THEN i.title ELSE '' END, '')
    """,
    # V3 node deletions.
    "MATCH (s:Session) DETACH DELETE s",
    "MATCH (e:Execution) DETACH DELETE e",
    "MATCH (e:ExecutionEnvironment) DETACH DELETE e",
    # Sandbox nodes lose their dead links (fields simply become unused).
    """
    MATCH (s:Sandbox)
    REMOVE s.environment_uid, s.ticket_uid, s.execution_uid
    """,
]


async def migrate() -> None:
    configure_neomodel()
    for stmt in _STATEMENTS:
        results, _ = await adb.cypher_query(stmt)
        print(f"ok: {' '.join(stmt.split())[:80]}…")
    print("V3 migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
