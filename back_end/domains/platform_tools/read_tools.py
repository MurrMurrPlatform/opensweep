"""Read-tools registry — file/code readers for the `internal_llm` executor;
OpenSweep-data readers (opensweep_*) for ALL executors (incl. claude_code / codex /
opencode) since they can't query OpenSweep's graph natively.

PLATFORM.md §Internal LLM read tools: the 4 file-reading tools are still
internal-only because delegated executors do their own filesystem reads.
The opensweep_* tools are platform data reads, distinct from filesystem reads,
and are required for the look-before-write contract in Discover/Maintain/Audit.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from domains.platform_tools.prior_findings import prior_findings
from domains.platform_tools.read_code import read_code
from domains.platform_tools.read_findings import (
    opensweep_get_finding,
    opensweep_list_findings,
    opensweep_search_findings,
)
from domains.platform_tools.docs_tools import list_docs, read_doc
from domains.platform_tools.memory_tools import search_memory
from domains.platform_tools.news_tools import list_interests, list_news_items
from domains.platform_tools.trace import trace
from domains.platform_tools.web_tools import fetch_url, web_search


READ_TOOLS: dict[str, Callable[..., Awaitable[Any]]] = {
    # Filesystem / code readers (internal_llm only)
    "read_code": read_code,
    "trace": trace,
    "prior_findings": prior_findings,
    # OpenSweep-data readers (look-before-write contract; all executors)
    "list_docs": list_docs,
    "read_doc": read_doc,
    "search_memory": search_memory,
    "opensweep_list_findings": opensweep_list_findings,
    "opensweep_search_findings": opensweep_search_findings,
    "opensweep_get_finding": opensweep_get_finding,
    # News radar readers + open-web research (news-scout; read-only)
    "list_news_items": list_news_items,
    "list_interests": list_interests,
    "web_search": web_search,
    "fetch_url": fetch_url,
}


def read_tool_names() -> list[str]:
    return sorted(READ_TOOLS.keys())


async def call_read_tool(name: str, **kwargs: Any) -> Any:
    if name not in READ_TOOLS:
        raise KeyError(f"unknown read tool: {name}")
    return await READ_TOOLS[name](**kwargs)
