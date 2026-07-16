"""Platform tools: list_docs / read_doc / propose_doc_edit /
confirm_doc_current (KNOWLEDGE_V3).

Replaces propose_knowledge_update + the knowledge read tools. Doc edits
write platform state, not repository state, so they are available in every
playbook including analyze-only — no change dial involved: proposals always
land as pending DocEdits for human review.
"""

from __future__ import annotations

from typing import Any

from domains.docs.models import Doc, doc_is_stale
from domains.docs.services import doc_freshness, doc_service


async def list_docs(*, repository_uid: str, **_: Any) -> list[dict[str, Any]]:
    """List this repository's documentation pages: slug, title, summary,
    pinned, watch_paths, stale. Pinned pages are already in your prompt;
    fetch the others with read_doc. Stale pages have had code changes under
    their watch_paths since their last review — distrust them until
    verified."""
    docs = [d for d in await Doc.nodes.all() if d.repository_uid == repository_uid]
    docs.sort(key=lambda d: (not bool(d.pinned), d.slug))
    return [
        {
            "slug": d.slug,
            "title": d.title or "",
            "summary": d.summary or "",
            "pinned": bool(d.pinned),
            "watch_paths": list(d.watch_paths or []),
            "stale": doc_is_stale(d),
        }
        for d in docs
    ]


async def read_doc(*, repository_uid: str, slug: str, **_: Any) -> dict[str, Any]:
    """Fetch one documentation page's full body by slug."""
    d = await doc_service.get_doc_by_slug(repository_uid, doc_service.normalize_slug(slug))
    if d is None:
        return {"status": "not_found", "slug": slug}
    return {
        "status": "ok",
        "slug": d.slug,
        "title": d.title or "",
        "summary": d.summary or "",
        "body": d.body or "",
        "pinned": bool(d.pinned),
        "watch_paths": list(d.watch_paths or []),
        "stale": doc_is_stale(d),
        "stale_paths": list(d.stale_paths or []),
    }


async def propose_doc_edit(
    *,
    repository_uid: str,
    proposed_body: str,
    rationale: str = "",
    slug: str = "",
    title: str = "",
    summary: str = "",
    watch_paths: list[str] | None = None,
    source_run_uid: str = "",
    executor: str = "",
    **_: Any,
) -> dict[str, Any]:
    """Propose a full replacement body for a documentation page (existing
    slug) or a new page (new slug + title + summary + watch_paths). Slugs
    are path-like — "backend/queue-workers" files the page under the
    backend folder. Set watch_paths to the repository paths the page
    describes so code changes there mark it for review. Lands as a pending
    edit for human review — read the current page first with read_doc and
    keep pages small: prefer pruning stale prose over adding new prose."""
    e = await doc_service.propose_doc_edit(
        repository_uid=repository_uid,
        proposed_body=proposed_body,
        rationale=rationale,
        slug=slug,
        title=title,
        summary=summary,
        watch_paths=watch_paths,
        source_run_uid=source_run_uid or "",
    )
    return {
        "status": "ok",
        "doc_edit_uid": e.uid,
        "doc_uid": e.doc_uid or "",
        "new_page": not bool(e.doc_uid),
    }


async def confirm_doc_current(
    *,
    repository_uid: str,
    slug: str,
    **_: Any,
) -> dict[str, Any]:
    """You verified this page against the current code and it is still
    accurate: stamp the review so its stale flag clears. Only call this
    after actually checking the page's claims — never to silence a stale
    marker you did not verify."""
    d = await doc_freshness.confirm_doc_current(repository_uid, slug)
    if d is None:
        return {"status": "not_found", "slug": slug}
    return {"status": "ok", "slug": d.slug}
