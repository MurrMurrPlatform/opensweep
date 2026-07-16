"""First-turn prompt briefing (KNOWLEDGE_V3_DOCUMENTATION.md §3).

One shared builder every dispatch path uses: pinned Docs verbatim, targeted
Docs verbatim, a folder-grouped one-line index of the remaining pages
(fetch via read_doc), and the memories anchored to the run's target docs.
Prompt cost stays proportional to relevance — everything else is on-demand
through the tools.
"""

from __future__ import annotations

from domains.docs.models import Doc, doc_is_stale
from domains.memory.services.memory_service import search_memory


def _index_line(d: Doc) -> str:
    line = f"- {d.slug}: {d.title or d.slug}"
    if d.summary:
        line += f" — {d.summary}"
    if doc_is_stale(d):
        line += " (code changed since last review)"
    return line


def _grouped_index(docs: list[Doc]) -> str:
    """Root pages first, then pages grouped by top-level folder."""
    root = [d for d in docs if "/" not in d.slug]
    folders: dict[str, list[Doc]] = {}
    for d in docs:
        if "/" in d.slug:
            folders.setdefault(d.slug.split("/", 1)[0], []).append(d)
    lines = [_index_line(d) for d in root]
    for folder in sorted(folders):
        lines.append(f"{folder}/")
        lines.extend(_index_line(d) for d in folders[folder])
    return "\n".join(lines)


async def build_briefing(
    *,
    repository_uid: str,
    target_doc_uids: list[str] | None = None,
) -> str:
    docs = [d for d in await Doc.nodes.all() if d.repository_uid == repository_uid]
    docs.sort(key=lambda d: d.slug)
    target_uids = set(target_doc_uids or [])
    inlined = [d for d in docs if d.pinned or d.uid in target_uids]
    indexed = [d for d in docs if not (d.pinned or d.uid in target_uids)]

    sections: list[str] = []

    if inlined:
        pages = "\n\n".join(
            f"### {d.title or d.slug}\n\n{d.body}".strip()
            for d in inlined
            if (d.body or "").strip()
        )
        if pages:
            sections.append(f"## Repository documentation\n\n{pages}")

    if indexed:
        sections.append(
            "## Other documentation pages (fetch with read_doc)\n\n"
            + _grouped_index(indexed)
        )

    memories = []
    for anchor_uid in target_doc_uids or []:
        memories.extend(
            await search_memory(repository_uid=repository_uid, anchor_uid=anchor_uid, limit=10)
        )
    if memories:
        seen: set[str] = set()
        lines: list[str] = []
        for m in memories:
            if m.uid in seen:
                continue
            seen.add(m.uid)
            stale = " (possibly stale — code changed since)" if m.possibly_stale else ""
            lines.append(f"- **{m.title}**{stale}: {m.body}".rstrip(": "))
        sections.append(
            "## Memories for this target (search more with search_memory)\n\n" + "\n".join(lines)
        )

    return "\n\n".join(sections).strip()
