"""Memory service (KNOWLEDGE_V3_MEMORY.md).

write_memory is an upsert: an identical fingerprint touches the existing
row; a same-titled memory on the same (repo, anchor) is overwritten. Search
is substring over title+body with fresh-before-stale ranking. Staleness is a
query, not a state.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException

from domains.memory.models import Memory
from domains.memory.schemas import MemoryDTO
from infrastructure.audit import write_audit


def _fingerprint(title: str, body: str) -> str:
    normalized = f"{(title or '').strip().lower()}\n{(body or '').strip()}"
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:24]


async def _anchor_change_times(repository_uid: str) -> dict[str, datetime]:
    from domains.docs.models import Doc

    return {
        d.uid: d.code_changed_at
        for d in await Doc.nodes.filter(repository_uid=repository_uid)
        if d.code_changed_at
    }


def _possibly_stale(m: Memory, change_times: dict[str, datetime]) -> bool:
    if not m.anchor_uid or m.updated_at is None:
        return False
    changed = change_times.get(m.anchor_uid)
    return bool(changed and changed > m.updated_at)


def memory_to_dto(m: Memory, *, possibly_stale: bool = False) -> MemoryDTO:
    return MemoryDTO(
        uid=m.uid,
        repository_uid=m.repository_uid,
        anchor_uid=m.anchor_uid or "",
        title=m.title,
        body=m.body or "",
        source_run_uid=m.source_run_uid or "",
        possibly_stale=possibly_stale,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


async def write_memory(
    *,
    repository_uid: str,
    title: str,
    body: str,
    anchor_uid: str = "",
    source_run_uid: str = "",
) -> dict:
    """Upsert a memory. Returns {status, memory_uid}."""
    title = (title or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    fingerprint = _fingerprint(title, body)
    title_lc = title.lower()

    duplicate: Memory | None = None
    same_title: Memory | None = None
    for m in await Memory.nodes.filter(repository_uid=repository_uid):
        if m.fingerprint == fingerprint and (m.anchor_uid or "") == (anchor_uid or ""):
            duplicate = m
            break
        if (m.title or "").strip().lower() == title_lc and (m.anchor_uid or "") == (anchor_uid or ""):
            same_title = m

    now = datetime.now(UTC)
    if duplicate is not None:
        duplicate.updated_at = now
        if source_run_uid:
            duplicate.source_run_uid = source_run_uid
        await duplicate.save()
        return {"status": "duplicate", "memory_uid": duplicate.uid}

    if same_title is not None:
        same_title.body = body
        same_title.fingerprint = fingerprint
        same_title.updated_at = now
        if source_run_uid:
            same_title.source_run_uid = source_run_uid
        await same_title.save()
        await write_audit(
            kind="memory.updated",
            subject_uid=same_title.uid,
            subject_type="Memory",
            actor_uid=source_run_uid or "agent",
            payload={"title": title},
        )
        return {"status": "updated", "memory_uid": same_title.uid}

    m = Memory(
        uid=uuid4().hex,
        repository_uid=repository_uid,
        anchor_uid=anchor_uid or "",
        title=title,
        body=body,
        fingerprint=fingerprint,
        source_run_uid=source_run_uid or "",
    )
    await m.save()
    await write_audit(
        kind="memory.created",
        subject_uid=m.uid,
        subject_type="Memory",
        actor_uid=source_run_uid or "agent",
        payload={"title": title, "anchor_uid": anchor_uid or ""},
    )
    return {"status": "created", "memory_uid": m.uid}


async def search_memory(
    *,
    repository_uid: str,
    query: str = "",
    anchor_uid: str = "",
    limit: int = 10,
) -> list[MemoryDTO]:
    """Substring search over title+body, fresh-before-stale, newest first.
    Returns full bodies — memories are small; there is no get tool."""
    q = (query or "").strip().lower()
    change_times = await _anchor_change_times(repository_uid)
    matched: list[tuple[bool, datetime, Memory]] = []
    for m in await Memory.nodes.filter(repository_uid=repository_uid):
        if anchor_uid and (m.anchor_uid or "") != anchor_uid:
            continue
        if q and q not in f"{m.title or ''}\n{m.body or ''}".lower():
            continue
        stale = _possibly_stale(m, change_times)
        matched.append((stale, m.updated_at or datetime.min.replace(tzinfo=UTC), m))
    matched.sort(key=lambda t: (t[0], -t[1].timestamp()))
    return [memory_to_dto(m, possibly_stale=stale) for stale, _, m in matched[: max(1, limit)]]


async def list_memories(
    *,
    repository_uid: str,
    anchor_uid: str = "",
    query: str = "",
    limit: int = 200,
) -> list[MemoryDTO]:
    return await search_memory(
        repository_uid=repository_uid, query=query, anchor_uid=anchor_uid, limit=limit
    )


async def delete_memory(uid: str, *, actor: str = "human") -> None:
    m = await Memory.nodes.get_or_none(uid=uid)
    if m is None:
        raise HTTPException(status_code=404, detail=f"Memory {uid} not found")
    await write_audit(
        kind="memory.deleted",
        subject_uid=m.uid,
        subject_type="Memory",
        actor_uid=actor,
        payload={"title": m.title},
    )
    await m.delete()
