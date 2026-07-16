"""Per-repo static-analyzer config — which deterministic tools feed
review/ask runs candidate lists (domains/execution/services/static_analysis.py).

Shape (Repository.analyzers JSONProperty):

    {"mode": "auto",            # auto (ecosystem detection) | custom | off
     "tools": [                 # used only when mode == "custom"
       {"tool": "ruff", "args": [], "paths": []},
       {"tool": "semgrep", "args": ["--config", "p/ci"], "paths": ["back_end/"]}]}

Mirrors workflow.py: normalize on read, validate on write (422), never
store junk keys.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from domains.execution.services.static_analysis import ANALYZER_MODES, ANALYZER_TOOLS
from domains.repositories.models import Repository


def _normalize(raw: dict | None) -> dict[str, Any]:
    raw = dict(raw or {})
    mode = str(raw.get("mode") or "auto")
    if mode not in ANALYZER_MODES:
        mode = "auto"
    tools = []
    for entry in raw.get("tools") or []:
        entry = dict(entry or {})
        if entry.get("tool") not in ANALYZER_TOOLS:
            continue
        tools.append(
            {
                "tool": str(entry["tool"]),
                "args": [str(a) for a in entry.get("args") or []],
                "paths": [str(p) for p in entry.get("paths") or []],
            }
        )
    return {"mode": mode, "tools": tools}


async def get_analyzers(repository_uid: str) -> dict[str, Any]:
    repo = await Repository.nodes.get_or_none(uid=repository_uid)
    return _normalize(repo.analyzers if repo else None)


async def set_analyzers(repository_uid: str, config: dict[str, Any]) -> dict[str, Any]:
    repo = await Repository.nodes.get_or_none(uid=repository_uid)
    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repository {repository_uid} not found")
    mode = (config or {}).get("mode")
    if mode is not None and mode not in ANALYZER_MODES:
        raise HTTPException(
            status_code=422, detail=f"invalid mode {mode!r}; valid: {list(ANALYZER_MODES)}"
        )
    for entry in (config or {}).get("tools") or []:
        tool = (entry or {}).get("tool")
        if tool not in ANALYZER_TOOLS:
            raise HTTPException(
                status_code=422, detail=f"unknown analyzer {tool!r}; valid: {list(ANALYZER_TOOLS)}"
            )
    normalized = _normalize(config)
    repo.analyzers = normalized
    await repo.save()
    return normalized
