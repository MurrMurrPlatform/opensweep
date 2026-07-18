"""Platform tool: update_plan_step.

The implementation checklist (submitted with the plan, mirrored to
Ticket.plan.steps) stays in sync with reality: the agent marks each step
in_progress/done as it works. Writes OpenSweep state only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException


def _validate(*, thread_uid: str, step_id: str, status: str) -> None:
    from domains.threads.services.thread_service import PLAN_STEP_STATUSES

    if not (thread_uid or "").strip():
        raise HTTPException(status_code=422, detail="thread_uid is required")
    if not (step_id or "").strip():
        raise HTTPException(status_code=422, detail="step_id is required")
    if status not in PLAN_STEP_STATUSES:
        raise HTTPException(
            status_code=422, detail="status must be pending, in_progress, or done"
        )


async def update_plan_step(
    *,
    thread_uid: str,
    step_id: str,
    status: str,
    notes: str = "",
    executor: str = "manual",  # noqa: ARG001 — attribution parity with siblings
) -> dict[str, Any]:
    from domains.threads.models import Thread
    from domains.threads.services.thread_service import mirror_plan_to_ticket

    _validate(thread_uid=thread_uid, step_id=step_id, status=status)
    thread = await Thread.nodes.get_or_none(uid=thread_uid)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    steps = list(thread.plan_steps or [])
    for step in steps:
        if step.get("id") == step_id:
            step["status"] = status
            if notes:
                step["notes"] = str(notes)[:500]
            break
    else:
        raise HTTPException(status_code=404, detail=f"unknown step_id '{step_id}'")
    thread.plan_steps = steps
    thread.updated_at = datetime.now(UTC)
    await thread.save()
    await mirror_plan_to_ticket(thread)
    return {"thread_uid": thread_uid, "step_id": step_id, "status": status}
