"""Platform tools: search_memory / write_memory (KNOWLEDGE_V3).

Memories are live immediately (no approval pipeline) and cheap for humans
to delete. write_memory is an upsert with server-side dedup; there is no
get or delete tool — search returns full bodies, deletion is human.
"""

from __future__ import annotations

from typing import Any

from domains.memory.services import memory_service


async def search_memory(
    *,
    repository_uid: str,
    query: str = "",
    anchor_uid: str = "",
    limit: int = 10,
    **_: Any,
) -> list[dict[str, Any]]:
    """Search this repository's memories (facts prior runs learned that the
    code cannot express). Full-text over title+body; possibly_stale means
    the anchored code changed after the memory was written."""
    results = await memory_service.search_memory(
        repository_uid=repository_uid, query=query, anchor_uid=anchor_uid, limit=limit
    )
    return [
        {
            "uid": m.uid,
            "title": m.title,
            "body": m.body,
            "anchor_uid": m.anchor_uid,
            "possibly_stale": m.possibly_stale,
            "updated_at": m.updated_at.isoformat() if m.updated_at else None,
        }
        for m in results
    ]


async def write_memory(
    *,
    repository_uid: str,
    title: str,
    body: str,
    anchor_uid: str = "",
    source_run_uid: str = "",
    executor: str = "",
    **_: Any,
) -> dict[str, Any]:
    """Record a small durable fact future runs should know: a gotcha, a
    decision, a non-obvious constraint. One paragraph, not a document —
    anything derivable from the code does not belong here. Same-titled
    memories on the same anchor are overwritten."""
    return await memory_service.write_memory(
        repository_uid=repository_uid,
        title=title,
        body=body,
        anchor_uid=anchor_uid,
        source_run_uid=source_run_uid or "",
    )
