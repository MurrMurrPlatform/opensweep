"""Read tool (internal_llm only): load source by path.

GitHub-only: contents are fetched from the GitHub contents API (default
branch) instead of a local working copy.
"""

from __future__ import annotations

from typing import Any

from domains.repositories.models import Repository
from domains.repositories.services.github_service import GitHubService
from infrastructure.git_providers import get_provider_client

_MAX_BYTES = 64 * 1024  # 64KB per file; truncate beyond


def _normalize(path: str) -> str | None:
    """Repo-relative posix path; reject absolute paths and `..` escapes."""
    p = (path or "").strip().replace("\\", "/").lstrip("./")
    if not p or p.startswith("/") or ".." in p.split("/"):
        return None
    return p.rstrip("/")


async def read_code(
    *,
    repository_uid: str,
    path: str | None = None,
    max_files: int = 10,
) -> list[dict[str, Any]]:
    """Load source by repo-relative path (file or directory)."""
    repo = await Repository.nodes.get_or_none(uid=repository_uid)
    if repo is None or not (repo.github_owner and repo.github_repo):
        return []
    client = get_provider_client(repo)
    gh = GitHubService(client)

    targets: list[str] = []
    if path:
        targets.append(path)

    out: list[dict[str, Any]] = []
    for raw in targets[:max_files]:
        t = _normalize(raw)
        if t is None:
            continue
        result = await gh.get_file_contents(repo.github_owner, repo.github_repo, t)
        if result is not None:
            text, _size = result
            data = text.encode("utf-8")[:_MAX_BYTES]
            out.append(
                {
                    "path": t,
                    "kind": "file",
                    "content": data.decode("utf-8", errors="replace"),
                    "bytes": len(data),
                }
            )
            continue
        # Might be a directory — the contents API returns a listing for dirs.
        try:
            listing = await client.get_file_contents(repo.github_owner, repo.github_repo, t)
        except Exception:
            continue
        if isinstance(listing, list):
            files = [
                str(entry.get("path") or "")
                for entry in listing
                if entry.get("type") == "file"
            ][:50]
            out.append({"path": t, "kind": "dir", "children": files})
    return out
