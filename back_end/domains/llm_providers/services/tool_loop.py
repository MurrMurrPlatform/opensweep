"""Multi-turn OpenAI tool-calling loop for HTTP providers.

Drives an `LLMProvider` (HTTP / OpenAI-compatible) through a conversation:
  1. Send messages + tools.
  2. If the assistant reply has tool_calls, execute each one, append the
     `tool` result messages, and loop.
  3. Stop when the assistant returns without tool_calls, when the iteration
     cap is hit, or on transport/timeout error.

The caller passes:
  - `tools`: OpenAI tool schemas (list[dict])
  - `executor`: async callable `(name, arguments_json) -> result_dict`
  - `on_event`: optional async callback for live trace updates
        await on_event(kind, payload)
        kinds: "assistant_chunk"   payload={"delta": "..."}
               "tool_call_started" payload={"name", "arguments_json", "id", "iter"}
               "tool_call_result"  payload={"id", "result"}
               "iteration_done"    payload={"iter", "assistant_text"}
               "stopped"           payload={"reason"}
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from domains.llm_providers.models import LLMProvider

ToolExecutor = Callable[[str, str], Awaitable[dict[str, Any]]]
EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class ToolLoopResult:
    iterations: int = 0
    assistant_final: str = ""
    tool_calls: list[dict] = field(default_factory=list)  # {name, arguments_json, result}
    error: str = ""
    duration_ms: int = 0
    transport: str = "http"
    command_excerpt: str = ""
    exit_code: int | None = None
    stopped_reason: str = ""


async def invoke_tool_loop(
    provider: LLMProvider,
    *,
    system_prompt: str,
    instruction: str,
    tools: list[dict],
    executor: ToolExecutor,
    on_event: EventCallback | None = None,
    max_iterations: int = 6,
    timeout_seconds: int = 240,
) -> ToolLoopResult:
    kind = (provider.kind or "").strip()
    base = (provider.base_url or "").rstrip("/")
    result = ToolLoopResult(transport="http")
    if not base:
        result.error = "base_url is empty"
        return result

    url = f"{base}/chat/completions"
    result.command_excerpt = f"POST {url} model={provider.model} max_iter={max_iterations}"

    headers = {"Content-Type": "application/json"}
    api_key = _resolve_api_key(provider)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": instruction},
    ]
    extra = _parse_extra_args(provider.extra_args or "")
    max_tokens = int(extra.pop("max_tokens", 4096))
    temperature = float(extra.pop("temperature", 0.2))

    started = time.monotonic()
    http_timeout = httpx.Timeout(timeout_seconds, connect=10.0)

    try:
        async with httpx.AsyncClient(timeout=http_timeout) as client:
            for it in range(1, max_iterations + 1):
                result.iterations = it
                payload = {
                    "model": provider.model or "",
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    **extra,
                }
                try:
                    resp = await client.post(url, headers=headers, json=payload)
                except httpx.HTTPError as exc:
                    result.error = f"{type(exc).__name__}: {exc}"[:500]
                    result.exit_code = -1
                    break
                result.exit_code = resp.status_code
                if resp.status_code >= 400:
                    result.error = f"HTTP {resp.status_code}: {resp.text[:400]}"
                    break
                try:
                    data = resp.json()
                except ValueError as exc:
                    result.error = f"non-JSON response: {exc}"
                    break

                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                assistant_text = _stringify_content(msg.get("content"))
                tool_calls = msg.get("tool_calls") or []

                if on_event and assistant_text:
                    await _safe(on_event, "assistant_chunk", {"delta": assistant_text, "iter": it})

                # Mirror the assistant's turn into our message list so the
                # next iteration has full context.
                messages.append({
                    "role": "assistant",
                    "content": assistant_text or "",
                    "tool_calls": tool_calls or None,
                })

                if not tool_calls:
                    result.assistant_final = assistant_text
                    result.stopped_reason = "model returned without tool_calls"
                    if on_event:
                        await _safe(on_event, "iteration_done", {"iter": it, "assistant_text": assistant_text})
                    break

                # Execute every tool call, append result messages.
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    fn = tc.get("function") or {}
                    name = fn.get("name", "")
                    args_json = fn.get("arguments", "") or "{}"
                    call_id = tc.get("id") or f"call-{it}-{name}"

                    if on_event:
                        await _safe(on_event, "tool_call_started", {
                            "id": call_id, "name": name, "arguments_json": args_json, "iter": it,
                        })

                    tool_result = await executor(name, args_json)
                    result.tool_calls.append({
                        "id": call_id, "name": name,
                        "arguments_json": args_json, "result": tool_result,
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": name,
                        "content": json.dumps(tool_result)[:8192],
                    })
                    if on_event:
                        await _safe(on_event, "tool_call_result", {
                            "id": call_id, "result": tool_result,
                        })

                if on_event:
                    await _safe(on_event, "iteration_done",
                                {"iter": it, "assistant_text": assistant_text})
            else:
                result.stopped_reason = f"hit max_iterations={max_iterations}"
                if on_event:
                    await _safe(on_event, "stopped", {"reason": result.stopped_reason})
    finally:
        result.duration_ms = int((time.monotonic() - started) * 1000)
    return result


def _resolve_api_key(provider: LLMProvider) -> str:
    import os

    from domains.llm_providers.services.credentials import provider_secret

    secret = provider_secret(provider)
    if secret:
        return secret
    env = (provider.api_key_env or "").strip()
    if env:
        return os.environ.get(env, "")
    return ""


def _parse_extra_args(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _stringify_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                parts.append(p["text"])
            else:
                parts.append(str(p))
        return "".join(parts)
    return str(content)


async def _safe(cb: EventCallback, kind: str, payload: dict) -> None:
    try:
        await cb(kind, payload)
    except Exception:
        # Trace callbacks must never break the loop.
        pass
