"""Plain-language narration for run transcripts (unified dev flow Phase 2).

Deterministic template narrator: every tool_use event gets a one-line,
human-readable description of what the agent is doing right now. Lines are
appended to the same events stream as `narration` events carrying
`covers_seq` (the seq of the tool_use they describe) so the UI can render a
readable feed and expand any line into the raw tool call underneath.

Pure by design — no LLM call, no I/O — so narration can never slow down or
degrade a run, and it works identically for every executor (the normalized
event stream is the input). An LLM-written narration layer can slot in
later behind the same event type.
"""

from __future__ import annotations

import json
from typing import Any

_MAX = 140


def _short(value: Any, limit: int = _MAX) -> str:
    text = str(value or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _first(inp: dict, *keys: str) -> str:
    for k in keys:
        v = inp.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def narrate_tool_use(name: str, tool_input: dict | str | None) -> str | None:
    """One plain-language line for a tool call, or None to stay silent.

    Durable events store `input` as a JSON-parseable preview string
    (stream_events.preview_structured); plain dicts and raw strings are
    accepted too so every executor path narrates.
    """
    inp: dict = {}
    raw = ""
    if isinstance(tool_input, dict):
        inp = tool_input
    elif isinstance(tool_input, str) and tool_input.strip():
        try:
            parsed = json.loads(tool_input)
            inp = parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            raw = tool_input.strip()
    n = (name or "").strip()
    low = n.lower()

    path = _first(inp, "file_path", "path", "notebook_path") or raw
    pattern = _first(inp, "pattern", "query", "glob") or raw
    command = _first(inp, "command", "cmd") or raw

    if low in {"read", "notebookread"} or low.endswith("read_file"):
        return f"Reading {_short(path) or 'a file'}"
    if low in {"edit", "write", "multiedit", "notebookedit"}:
        verb = "Writing" if low == "write" else "Editing"
        return f"{verb} {_short(path) or 'a file'}"
    if low in {"bash", "shell", "run_terminal_cmd", "exec"}:
        return f"Running `{_short(command, 100)}`" if command else "Running a shell command"
    if low in {"grep", "glob", "search", "codebase_search", "ls"}:
        target = pattern or path
        return f"Searching for {_short(target, 80)}" if target else "Searching the codebase"
    if low in {"webfetch", "fetch_url"}:
        return f"Fetching {_short(_first(inp, 'url'), 100) or 'a page'}"
    if low in {"websearch", "web_search"}:
        return f"Searching the web for {_short(pattern or _first(inp, 'query'), 80)}"
    if low == "todowrite":
        return "Updating its working plan"
    if low.startswith("mcp__") or low.startswith("opensweep_platform_") or low in {
        "create_finding",
        "update_finding",
        "update_ticket",
        "attach_artifact",
        "submit_thread_plan",
        "propose_doc_edit",
        "write_memory",
        "complete_run",
        "submit_verdict",
        "attach_fix",
    }:
        tool = low.removeprefix("mcp__").removeprefix("opensweep_platform_")
        tool = tool.split("__")[-1]
        friendly = {
            "create_finding": "Filing a finding",
            "update_finding": "Updating a finding",
            "update_ticket": "Updating the ticket",
            "attach_artifact": "Attaching supporting material",
            "submit_thread_plan": "Writing the implementation plan",
            "propose_doc_edit": "Proposing a documentation update",
            "write_memory": "Writing a note for its future self",
            "complete_run": "Wrapping up and summarizing",
            "submit_verdict": "Submitting its review verdict",
            "attach_fix": "Recording a fix for a review finding",
            "read_doc": "Reading project documentation",
            "list_docs": "Browsing project documentation",
            "search_memory": "Searching its memories",
            "ask_question": "Asking a question",
        }.get(tool)
        return friendly or f"Using the {tool.replace('_', ' ')} tool"
    if not n:
        return None
    return f"Using the {_short(n, 60)} tool"


def narration_for_event(event: dict) -> dict | None:
    """Build the narration event payload for a durable transcript event.

    Only tool_use events narrate — prose (assistant_text / user_message) is
    already human-readable and renders directly in the feed.
    """
    if event.get("type") != "tool_use":
        return None
    text = narrate_tool_use(event.get("name") or "", event.get("input"))
    if not text:
        return None
    return {"text": text, "covers_seq": event.get("seq", 0)}
