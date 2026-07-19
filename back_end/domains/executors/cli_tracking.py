"""Tracking-only CLI executor adapters for Codex and OpenCode.

These adapters invoke the active CLI provider and parse a final JSON envelope
of platform-tool calls. They are deliberately read/report only: no patch or
apply surface is available in v1.

Shared plumbing (provider/ceiling resolution, stream recording, envelope
extraction + tool dispatch, live ceilings) lives in `_shared.py`.
"""

from __future__ import annotations

import json
import time
from typing import Any

from domains.executors._shared import (
    StreamRecorder,
    budget_briefing,
    ceiling_warnings,
    execute_envelope_tool_calls,
    extract_envelope,
    record_input,
    resolve_provider,
    resolve_wall_ceiling,
)
from domains.executors.base import AdapterRegistry, DispatchRequest, DispatchResult, ExecutorAdapter
from domains.executors.quota import detect_quota_exhaustion
from domains.investigations.schemas import Executor, RunStatus
from domains.investigations.services.run_events import append_event
from domains.llm_providers.services.llm_executor import (
    invoke as invoke_provider,
)
from domains.platform_tools.complete_run import extract_outcome
from domains.run_policies.services.ceilings import UsageSnapshot
from infrastructure import artifact_store
from infrastructure.code_graph import CODE_GRAPH_PROMPT, code_graph_available

# Patch tools stay off in tracking-only v1.
_DENY_TOOLS = {"attach_patch_to_finding": "patch tools are disabled in tracking-only v1"}


class _CLITrackingAdapter(ExecutorAdapter):
    provider_kind: str
    name: Executor

    async def dispatch(self, req: DispatchRequest) -> DispatchResult:
        started = time.monotonic()
        provider = await resolve_provider(
            req.provider_uid, kind=self.provider_kind, repository_uid=req.repository_uid
        )
        if provider is None:
            return DispatchResult(
                status=RunStatus.FAILED,
                error=f"active provider is not kind={self.provider_kind}",
                summary=f"{self.name.value} requires the active provider to be {self.provider_kind}",
            )

        if req.model_override:
            # In-memory only — per-stage workflow override, never saved.
            provider.model = req.model_override

        timeout = resolve_wall_ceiling(req, provider.kind)
        instruction = _instruction(req, timeout)
        # Both CLIs get the code-graph MCP server over the workspace clone —
        # opencode through its generated config, codex through `-c` argv
        # overrides (llm_executor) — under this same availability gate.
        system_prompt = _SYSTEM_PROMPT
        if code_graph_available(req.repository_local_path or ""):
            system_prompt = _SYSTEM_PROMPT + "\n" + CODE_GRAPH_PROMPT
        await record_input(
            req.run_uid,
            system_prompt=system_prompt,
            instruction=instruction,
        )
        append_event(req.run_uid, "user_message", text=instruction)

        # on_chunk delivers the running TOTAL per stream; the transcript wants
        # only the new tail, as assistant_text chunks (consecutive chunks merge
        # in the UI — codex/opencode CLIs have no structured event stream here).
        streamed_len = {"stdout": 0}
        recorder = StreamRecorder(
            run_uid=req.run_uid,
            repository_uid=req.repository_uid,
            label=f"live {self.name.value} transcript",
        )

        async def _on_chunk(stream: str, text: str) -> None:
            if stream == "stdout":
                delta = text[streamed_len["stdout"]:]
                if delta:
                    streamed_len["stdout"] = len(text)
                    append_event(req.run_uid, "assistant_text", text=delta)
            await recorder.record_total(stream, text)

        try:
            inv = await invoke_provider(
                provider,
                system_prompt=system_prompt,
                instruction=instruction,
                timeout_seconds=timeout,
                working_dir=req.repository_local_path,
                on_chunk=_on_chunk,
                run_uid=req.run_uid,
            )
        finally:
            await recorder.close()
        wall = time.monotonic() - started
        raw_uri = artifact_store.put(
            repository_uid=req.repository_uid,
            run_uid=req.run_uid,
            content=(inv.raw_output or "") + ("\n--- STDERR ---\n" + inv.stderr if inv.stderr else ""),
            artifact_type="raw_transcript",
            extension="txt",
            summary=f"{self.name.value} raw transcript",
        )

        envelope = extract_envelope(inv.raw_output or "")
        parse_status = "ok" if envelope else "degraded"

        # Quota is a state, not a failure (§8): pause instead of failing when
        # the CLI died on a usage/rate limit. A completed tool flow (a parsed
        # envelope) is agent SUCCESS and is never treated as quota.
        if envelope is None and detect_quota_exhaustion(
            inv.exit_code, inv.raw_output or "", inv.stderr or ""
        ):
            return DispatchResult(
                status=RunStatus.PAUSED_QUOTA,
                raw_artifact_uri=raw_uri,
                parse_status=parse_status,
                usage={
                    "wall_seconds": round(wall, 2),
                    "exit_code": inv.exit_code,
                    "provider_kind": provider.kind,
                    "transport": inv.transport,
                },
                error="provider quota/rate limit reached",
                summary=f"{self.name.value} paused: provider quota exhausted — will retry",
            )

        tool_results: list[dict[str, Any]] = []
        output_refs: list[str] = [raw_uri]
        outcome: dict[str, Any] = {}
        if envelope:
            tool_results, refs, outcome = await execute_envelope_tool_calls(
                calls=envelope.get("tool_calls"),
                req=req,
                executor_value=self.name.value,
                deny_tools=_DENY_TOOLS,
            )
            output_refs.extend(refs)

        # Post-run ceiling accounting (Task 5): warnings only — a finished run
        # is never retroactively failed; LIMIT_EXCEEDED is reserved for runs a
        # limit actually stopped (wall kill surfaces as inv.error "timed out").
        usage_snapshot = UsageSnapshot(
            wall_seconds=wall,
            tool_turns=len(envelope.get("tool_calls", [])) if envelope else 0,
        )
        warnings = ceiling_warnings(
            policy=req.policy, usage=usage_snapshot, wall_ceiling=timeout
        )

        wall_killed = inv.error.startswith("timed out") if inv.error else False
        if wall_killed:
            status = RunStatus.LIMIT_EXCEEDED
        elif inv.error:
            status = RunStatus.FAILED
        else:
            status = RunStatus.AWAITING_INPUT
        return DispatchResult(
            status=status,
            raw_artifact_uri=raw_uri,
            parse_status=parse_status,
            usage={
                "wall_seconds": round(wall, 2),
                "exit_code": inv.exit_code,
                "provider_kind": provider.kind,
                "transport": inv.transport,
                "tool_calls": len(envelope.get("tool_calls", [])) if envelope else 0,
                "tool_results": tool_results,
                "warnings": warnings,
            },
            output_refs=output_refs,
            error=inv.error or "",
            summary=f"{self.name.value} finished in {wall:.1f}s",
            outcome=outcome or extract_outcome({"summary": (envelope or {}).get("summary")}),
        )


class CodexAdapter(_CLITrackingAdapter):
    name = Executor.CODEX
    provider_kind = "codex_subscription"


class OpenCodeAdapter(_CLITrackingAdapter):
    name = Executor.OPENCODE
    provider_kind = "opencode"


_SYSTEM_PROMPT = """You are an investigative agent inside OpenSweep, a tracking-only
repo intelligence platform.

You may inspect code and run read-only commands. Do not edit files, create
patches, commit, open PRs, or apply changes.

At the end, return one JSON object:

```json
{
  "summary": "<short summary>",
  "tool_calls": [
    {"tool": "create_finding", "args": {...}},
    {"tool": "write_memory", "args": {...}},
    {"tool": "propose_doc_edit", "args": {...}},
    {"tool": "attach_artifact", "args": {...}},
    {"tool": "complete_run", "args": {
      "summary": "<one short paragraph on the run outcome>",
      "did": ["<what you did>"],
      "skipped": ["<what you skipped and why>"],
      "succeeded": ["<what succeeded>"],
      "failed": ["<what failed and why>"],
      "next_steps": ["<follow-ups or future suggestions>"]
    }}
  ]
}
```

Always end the tool_calls with that `complete_run` entry — one short sentence
per list item, omitting lists you have nothing for. It is stored on the Run
and shown to humans who did not watch the run.

Allowed tools are create_finding, update_finding, propose_doc_edit,
confirm_doc_current, write_memory, attach_artifact, and complete_run.

If `opensweep` MCP tools (opensweep_*) appear in your NATIVE tool list, prefer
calling them directly as you work — they land immediately with full
provenance. Do NOT repeat a call you already made natively in the final
JSON envelope; list only the calls you could not make plus the closing
`complete_run` entry. Without native opensweep_* tools, put every intended
call in the envelope as described above.

Treat incomplete or stale documentation inside the repository as a Finding
tagged `docs`. Use `write_memory` for small durable facts future runs should
know: gotchas, decisions, non-obvious constraints — one paragraph, never
anything derivable from the code. Use `propose_doc_edit` to improve OpenSweep's
documentation pages (conventions, architecture, features) when they are
wrong, missing, or bloated; proposals land as pending edits for human
review.
"""


def _instruction(req: DispatchRequest, wall_ceiling: int | None = None) -> str:
    return f"""# Run

repository_uid: {req.repository_uid}
run_uid: {req.run_uid}

# Intent

{req.intent}

# Target

```json
{json.dumps(req.target or {}, indent=2)}
```

{req.context or ""}

{budget_briefing(req.policy, wall_ceiling)}

Investigate only. Record bugs, gaps, and improvements through the final
JSON tool_calls envelope; persist durable facts with write_memory.
"""


AdapterRegistry.register(CodexAdapter())
AdapterRegistry.register(OpenCodeAdapter())
