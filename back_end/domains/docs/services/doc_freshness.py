"""Doc freshness — webhook-driven (KNOWLEDGE_V3_DOCUMENTATION.md §9).

GitHub-only: there is no local working copy whose mtimes can be walked.
GitHub `push` webhooks hand us the changed paths from the payload
(commits[*].added/modified/removed) and we mark the Doc pages watching them
stale — see api/v1/github_webhooks.py.

Staleness is derived (code_changed_at > last_reviewed_at), never stored.
It clears when the page is reviewed: a human edit, an accepted DocEdit, or
an explicit confirm_doc_current from a document run that verified the page
and found it still true. No LLM is involved here — pure path matching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from domains.docs.models import Doc
from logging_config import logger

# stale_paths is briefing material, not a changelog — keep it bounded.
_MAX_STALE_PATHS = 200


@dataclass
class DocStaleResult:
    docs_marked: int = 0
    errors: list[str] = field(default_factory=list)


def _normalize(path: str) -> str:
    return (path or "").strip().replace("\\", "/").lstrip("./").rstrip("/")


def watches_path(watch_paths: list[str], changed: str) -> bool:
    """True when `changed` equals a watched path or lives under a watched dir."""
    for raw in watch_paths:
        watched = _normalize(raw)
        if not watched:
            continue
        if changed == watched or changed.startswith(watched + "/"):
            return True
    return False


async def docs_watching_paths(repository_uid: str, paths: list[str]) -> list[str]:
    """Doc uids whose watch_paths cover any of the given repository paths.

    Lets a write run pre-load its likely-relevant pages into the first-turn
    briefing (inlined verbatim) before any code has changed — matched off the
    paths the run already knows about (a PR's findings, a ticket's linked
    findings). Returns [] when nothing matches; the briefing index + read_doc
    still cover every other page.
    """
    norm = [p for p in (_normalize(p) for p in paths) if p]
    if not norm:
        return []
    out: list[str] = []
    for d in await Doc.nodes.all():
        if d.repository_uid != repository_uid:
            continue
        if any(watches_path(list(d.watch_paths or []), p) for p in norm):
            out.append(d.uid)
    return out


async def mark_docs_stale(
    repository_uid: str,
    changed_paths: list[str],
    now: datetime | None = None,
) -> DocStaleResult:
    """Stamp code_changed_at + accumulate stale_paths on every Doc whose
    watch_paths match a changed path.

    Called from the GitHub push webhook. Best-effort per doc: one bad page
    never blocks the rest.
    """
    result = DocStaleResult()
    changed = [p for p in (_normalize(p) for p in changed_paths) if p]
    if not changed:
        return result
    now = now or datetime.now(UTC)

    docs = [d for d in await Doc.nodes.all() if d.repository_uid == repository_uid]
    for d in docs:
        try:
            hits = [p for p in changed if watches_path(list(d.watch_paths or []), p)]
            if not hits:
                continue
            d.code_changed_at = now
            merged = list(dict.fromkeys(list(d.stale_paths or []) + hits))
            d.stale_paths = merged[:_MAX_STALE_PATHS]
            await d.save()
            result.docs_marked += 1
        except Exception as exc:  # noqa: BLE001
            msg = f"doc={d.uid}: {type(exc).__name__}: {exc}"
            logger.warning(f"doc freshness: {msg}")
            result.errors.append(msg)
    return result


async def confirm_doc_current(repository_uid: str, slug: str) -> Doc | None:
    """A document run verified this page against the code and found it still
    true: stamp the review without an edit. Returns None for unknown slugs."""
    from domains.docs.services.doc_service import get_doc_by_slug, normalize_slug

    d = await get_doc_by_slug(repository_uid, normalize_slug(slug))
    if d is None:
        return None
    d.last_reviewed_at = datetime.now(UTC)
    d.stale_paths = []
    await d.save()
    return d
