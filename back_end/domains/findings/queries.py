"""Convenience read helpers for Findings."""

from domains.findings.models import Finding


async def find_similar(
    *,
    repository_uid: str,
    dedupe_key: str | None = None,
    title_substring: str | None = None,
) -> list[Finding]:
    """Return open Findings that look similar to the input. Cheap dedupe helper."""
    nodes = await Finding.nodes.all()
    out = []
    for f in nodes:
        if f.repository_uid != repository_uid:
            continue
        if f.status in ("dismissed", "wont-fix", "superseded"):
            continue
        if dedupe_key and f.dedupe_key == dedupe_key:
            out.append(f)
        elif title_substring and title_substring.lower() in (f.title or "").lower():
            out.append(f)
    return out
