"""Read tool (internal_llm only): trace a symbol/route/flow across files.

This is a deliberately shallow tracer in v1: it greps files fetched from the
GitHub contents API for a symbol/route. GitHub-only means there is no local
tree to walk, so the candidate file set comes from the union of the Doc
pages' watch_paths (directories are expanded one level via the contents
API). Deep AST-level tracing is a future enhancement.
"""

from __future__ import annotations

import fnmatch
import re
from typing import Any

from domains.docs.models import Doc
from domains.repositories.models import Repository
from domains.repositories.services.github_service import GitHubService
from infrastructure.git_providers import GitProviderClient, get_provider_client

_MAX_HITS = 50
_MAX_FILES = 40  # cap on GitHub contents fetches per trace call


def _matches_globs(path: str, file_globs: tuple[str, ...]) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(name, g) for g in file_globs)


async def _candidate_paths(
    repository_uid: str,
    *,
    owner: str,
    repo_name: str,
    file_globs: tuple[str, ...],
    client: GitProviderClient,
) -> list[str]:
    """Doc watch_paths, filtered by glob; directories expanded one level."""
    files: list[str] = []
    dirs: list[str] = []
    seen: set[str] = set()

    docs = [d for d in await Doc.nodes.all() if d.repository_uid == repository_uid]
    for doc in docs:
        for raw in doc.watch_paths or []:
            p = (raw or "").strip().replace("\\", "/").lstrip("./").rstrip("/")
            if not p or p in seen:
                continue
            seen.add(p)
            if _matches_globs(p, file_globs):
                files.append(p)
            else:
                dirs.append(p)

    for d in dirs:
        if len(files) >= _MAX_FILES:
            break
        try:
            listing = await client.get_file_contents(owner, repo_name, d)
        except Exception:
            continue
        if not isinstance(listing, list):
            continue
        for entry in listing:
            path = str(entry.get("path") or "")
            if entry.get("type") != "file" or not path or path in seen:
                continue
            seen.add(path)
            if _matches_globs(path, file_globs):
                files.append(path)

    return files[:_MAX_FILES]


async def trace(
    *,
    repository_uid: str,
    needle: str,
    file_globs: tuple[str, ...] = ("*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.vue"),
    max_hits: int = _MAX_HITS,
) -> dict[str, Any]:
    repo = await Repository.nodes.get_or_none(uid=repository_uid)
    if repo is None or not (repo.github_owner and repo.github_repo):
        return {"hits": []}

    client = get_provider_client(repo)
    gh = GitHubService(client)
    candidates = await _candidate_paths(
        repository_uid,
        owner=repo.github_owner,
        repo_name=repo.github_repo,
        file_globs=file_globs,
        client=client,
    )

    pattern = re.compile(re.escape(needle))
    hits: list[dict[str, Any]] = []

    for path in candidates:
        if len(hits) >= max_hits:
            break
        result = await gh.get_file_contents(repo.github_owner, repo.github_repo, path)
        if result is None:
            continue
        text, _size = result
        for n, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                hits.append(
                    {
                        "path": path,
                        "line": n,
                        "excerpt": line.strip()[:200],
                    }
                )
                if len(hits) >= max_hits:
                    break

    return {"hits": hits}
