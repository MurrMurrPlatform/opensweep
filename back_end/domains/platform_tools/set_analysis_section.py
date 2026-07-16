"""Platform tool: set_analysis_section.

Set (or replace) one narrative section of the deep-scan Analysis — executive
summary, repository map, security summary, implementation plan, top changes,
etc. Sections are an open dict keyed by `section`, so the agent can author
the report incrementally, one section per call, and add custom sections
without a schema change.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from domains.analysis.services.analysis_service import get_or_create_analysis


def _slugify_section(section: str) -> str:
    key = (section or "").strip().lower().replace(" ", "_").replace("-", "_")
    return "".join(c for c in key if c.isalnum() or c == "_")[:60]


async def set_analysis_section(
    *,
    repository_uid: str,
    source_run_uid: str,
    section: str,
    content: str,
    executor: str = "",
) -> dict[str, Any]:
    key = _slugify_section(section)
    if not key:
        raise HTTPException(status_code=422, detail="section must be a non-empty key")

    node = await get_or_create_analysis(
        repository_uid=repository_uid,
        source_run_uid=source_run_uid,
        executor=executor,
    )
    sections = dict(node.sections or {})
    sections[key] = content or ""
    node.sections = sections
    node.updated_at = datetime.now(UTC)
    await node.save()
    return {"analysis_uid": node.uid, "section": key}
