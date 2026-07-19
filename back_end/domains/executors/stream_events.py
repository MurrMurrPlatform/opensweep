"""claude `--output-format stream-json --verbose` → transcript events.

PLATFORM_V3_DESIGN.md §4: the server parses executor output into structured
transcript events; the frontend renders events and never sees raw stdout.

Stateful because tool_result stream lines carry only a `tool_use_id` — the
matching tool name arrives earlier on the tool_use block, so one translator
instance must live for the whole subprocess.
"""

from __future__ import annotations

import json
from typing import Any

from domains.runs.services.run_events import preview, preview_structured


def stream_event_delta(line: str) -> str | None:
    """Token-stream extraction for `--include-partial-messages` lines.

    Returns None when the line is NOT a stream_event (translate it normally),
    "" for stream_events that carry no displayable text (message_start, tool
    input json deltas, thinking, …), and the text fragment for
    content_block_delta/text_delta.

    Stream events are ephemeral by contract: the complete assistant/user
    message line that follows them is the durable transcript record, so
    callers must never append these to the events file or the raw artifact —
    they fan out to live watchers via publish_delta and are dropped.
    """
    s = (line or "").strip()
    if not s or '"stream_event"' not in s:
        return None
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or obj.get("type") != "stream_event":
        return None
    event = obj.get("event")
    if not isinstance(event, dict) or event.get("type") != "content_block_delta":
        return ""
    delta = event.get("delta")
    if isinstance(delta, dict) and delta.get("type") == "text_delta":
        text = delta.get("text")
        if isinstance(text, str):
            return text
    return ""


class ClaudeStreamTranslator:
    """One instance per claude subprocess; feed stdout lines, get events."""

    def __init__(self) -> None:
        self._tool_names: dict[str, str] = {}

    def translate(self, line: str) -> list[dict[str, Any]]:
        """Events contributed by one stdout line (possibly none).

        Shapes (claude CLI):
          {"type":"system","subtype":"init", …}                       → dropped
          {"type":"assistant","message":{"content":[text|tool_use]}}  → assistant_text / tool_use
          {"type":"user","message":{"content":[tool_result]}}         → tool_result
          {"type":"result","subtype":"success", …}                    → turn_end
        Non-JSON lines (operator overrode the output format) pass through as
        assistant_text so nothing is silently lost.
        """
        s = (line or "").strip()
        if not s:
            return []
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            return [{"type": "assistant_text", "text": line}]
        if not isinstance(obj, dict):
            return []

        event_type = obj.get("type")
        if event_type == "assistant":
            return self._from_assistant(obj)
        if event_type == "user":
            return self._from_user(obj)
        if event_type == "result":
            return [
                {
                    "type": "turn_end",
                    "status": str(obj.get("subtype") or ""),
                    "usage": _result_usage(obj),
                }
            ]
        return []

    def _from_assistant(self, obj: dict[str, Any]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for block in (obj.get("message") or {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                if block["text"]:
                    events.append({"type": "assistant_text", "text": block["text"]})
            elif block.get("type") == "tool_use":
                name = str(block.get("name") or "?")
                tool_use_id = str(block.get("id") or "")
                if tool_use_id:
                    self._tool_names[tool_use_id] = name
                events.append(
                    {
                        "type": "tool_use",
                        "name": name,
                        # JSON-parseable even when truncated — the UI renders
                        # Edit/Write inputs as real file diffs.
                        "input": preview_structured(block.get("input")),
                    }
                )
        return events

    def _from_user(self, obj: dict[str, Any]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for block in (obj.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            name = self._tool_names.get(str(block.get("tool_use_id") or ""), "?")
            events.append(
                {
                    "type": "tool_result",
                    "name": name,
                    "output": preview(_tool_result_text(block.get("content"))),
                    "is_error": bool(block.get("is_error")),
                }
            )
        return events


def _tool_result_text(content: Any) -> str:
    """tool_result content is a string or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p)
    return "" if content is None else str(content)


def _result_usage(obj: dict[str, Any]) -> dict[str, Any]:
    """Whitelist the useful bits of the claude `result` event."""
    usage: dict[str, Any] = {}
    for key in ("duration_ms", "duration_api_ms", "num_turns", "total_cost_usd"):
        if obj.get(key) is not None:
            usage[key] = obj[key]
    if isinstance(obj.get("usage"), dict):
        for key in ("input_tokens", "output_tokens"):
            if obj["usage"].get(key) is not None:
                usage[key] = obj["usage"][key]
    return usage
