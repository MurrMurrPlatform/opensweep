"""Platform tool: complete_run.

Finalizes an Run — sets status, persists usage proxies,
records output_refs, and stores the agent's end-of-run outcome summary
(what it did / skipped / succeeded / failed / next steps) on the Run node.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from domains.runs.models import Run
from infrastructure.audit import write_audit


def _clean_items(value: Any) -> list[str]:
    """Coerce an agent-supplied list into a list of non-empty strings."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def build_outcome(
    *,
    summary: str = "",
    did: Any = None,
    skipped: Any = None,
    succeeded: Any = None,
    failed: Any = None,
    next_steps: Any = None,
) -> dict[str, Any]:
    """Normalize the structured end-of-run summary. Empty sections drop out."""
    outcome: dict[str, Any] = {}
    if (summary or "").strip():
        outcome["text"] = summary.strip()
    for key, value in (
        ("did", did),
        ("skipped", skipped),
        ("succeeded", succeeded),
        ("failed", failed),
        ("next_steps", next_steps),
    ):
        items = _clean_items(value)
        if items:
            outcome[key] = items
    return outcome


_STRUCTURED_KEYS = {"did", "skipped", "succeeded", "failed", "next_steps"}

# Statuses a finalize call may legally leave a Run in. Validated here (not in
# the HTTP layer) so the HTTP, MCP, and dispatcher paths are all covered — a
# caller-supplied string must never land verbatim in Run.status.
VALID_FINAL_STATUSES = frozenset(
    {"awaiting_input", "completed", "ended", "failed", "limit_exceeded"}
)

# There is no terminal "completed" run state (see RunStatus): a finished turn
# is `awaiting_input` — the workspace stays alive for follow-up/review and the
# write-run finalize hook (validate → push → draft PR) keys on it. Agents
# naturally self-report success as "completed", so accept it but normalize to
# the canonical status. Without this a self-completing CLI write run is a
# dead-end: it accepts no follow-up (FOLLOW_UP_STATUSES) and its commit is
# never pushed (both the lifecycle stale-check and finalize_write_run gate on
# awaiting_input).
_COMPLETION_ALIASES = {"completed": "awaiting_input"}


def canonical_final_status(final_status: str) -> str:
    """Map a validated final_status onto the canonical RunStatus it means.

    Pure so the alias rule is unit-testable. Only "completed" → awaiting_input
    today; every other valid status passes through unchanged.
    """
    return _COMPLETION_ALIASES.get(final_status, final_status)


def merge_summary(
    existing: dict[str, Any], outcome: dict[str, Any]
) -> dict[str, Any]:
    """Decide what the Run's stored summary becomes.

    A structured summary always wins — the agent wrote it deliberately.
    Text-only input (e.g. the lifecycle's synthetic finalize summary) is a
    fallback: it never clobbers a structured summary the agent already left.
    """
    if outcome.keys() & _STRUCTURED_KEYS:
        return outcome
    if outcome and not (existing.keys() & _STRUCTURED_KEYS):
        return outcome
    return existing


def extract_outcome(args: dict[str, Any]) -> dict[str, Any]:
    """Harvest the structured summary from a trailer complete_run call's args."""
    return build_outcome(
        summary=str(args.get("summary") or ""),
        did=args.get("did"),
        skipped=args.get("skipped"),
        succeeded=args.get("succeeded"),
        failed=args.get("failed"),
        next_steps=args.get("next_steps"),
    )


async def complete_run(
    *,
    run_uid: str = "",
    summary: str = "",
    did: Any = None,
    skipped: Any = None,
    succeeded: Any = None,
    failed: Any = None,
    next_steps: Any = None,
    output_refs: Optional[list[str]] = None,
    usage: Optional[dict[str, Any]] = None,
    raw_artifact_uri: Optional[str] = None,
    parse_status: Optional[str] = None,
    error: Optional[str] = None,
    final_status: str = "awaiting_input",
    # Trailer tool-call paths setdefault these on every call; accept + ignore
    # so a complete_run trailer entry doesn't die on unexpected kwargs.
    source_run_uid: str = "",
    executor: str = "",
) -> dict[str, Any]:
    run_uid = run_uid or source_run_uid
    if final_status not in VALID_FINAL_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"invalid final_status {final_status!r}; "
                f"must be one of {sorted(VALID_FINAL_STATUSES)}"
            ),
        )
    final_status = canonical_final_status(final_status)
    r = await Run.nodes.get_or_none(uid=run_uid)
    if r is None:
        raise HTTPException(status_code=404, detail=f"Run {run_uid} not found")

    now = datetime.now(timezone.utc)
    r.status = final_status
    r.completed_at = now
    if usage:
        r.usage = {**(r.usage or {}), **usage}
    if output_refs:
        r.output_refs = list({*(r.output_refs or []), *output_refs})
    if raw_artifact_uri:
        r.raw_artifact_uri = raw_artifact_uri
    if parse_status:
        r.parse_status = parse_status
    if error:
        r.error = error
    outcome = build_outcome(
        summary=summary,
        did=did,
        skipped=skipped,
        succeeded=succeeded,
        failed=failed,
        next_steps=next_steps,
    )
    r.summary = merge_summary(dict(r.summary or {}), outcome)
    if r.started_at and not r.duration_ms:
        delta = (now - r.started_at).total_seconds() * 1000
        r.duration_ms = int(delta)
    r.updated_at = now
    await r.save()
    await write_audit(
        kind=f"run.{final_status}",
        subject_uid=r.uid,
        subject_type="Run",
        actor_uid=r.executor,
        payload={"summary": summary, "outcome": outcome, "usage": dict(r.usage or {})},
    )
    # Checked stamps are written by the playbook completion hook
    # (playbooks.on_turn_complete), not here — analyze playbooks only.
    return {
        "run_uid": r.uid,
        "status": r.status,
        "duration_ms": r.duration_ms,
    }
