"""Platform tool: add_analysis_note.

Append one item to a deep-scan Analysis's auditable lists:
- note_type="coverage"   → what area was examined/partial/skipped (the
  running checklist so no area is silently missed)
- note_type="strength"   → a positive observation (well-designed area)
- note_type="validation" → one row of the validation baseline (a check that
  was run/skipped and its result)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from fastapi import HTTPException

from domains.analysis.models import COVERAGE_STATUSES, NOTE_TYPES
from domains.analysis.services.analysis_service import get_or_create_analysis


async def add_analysis_note(
    *,
    repository_uid: str,
    source_run_uid: str,
    note_type: str,
    # coverage
    area: str = "",
    paths: Optional[list[str]] = None,
    status: str = "examined",
    note: str = "",
    # strength
    title: str = "",
    detail: str = "",
    # validation
    check: str = "",
    command: str = "",
    result: str = "",
    details: str = "",
    executor: str = "",
) -> dict[str, Any]:
    if note_type not in NOTE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid note_type={note_type!r}; expected one of {sorted(NOTE_TYPES)}",
        )
    if note_type == "coverage" and status not in COVERAGE_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid coverage status={status!r}; expected one of {sorted(COVERAGE_STATUSES)}",
        )

    node = await get_or_create_analysis(
        repository_uid=repository_uid,
        source_run_uid=source_run_uid,
        executor=executor,
    )

    if note_type == "coverage":
        field, item = "coverage", {
            "area": area,
            "paths": list(paths or []),
            "status": status,
            "note": note,
        }
    elif note_type == "strength":
        field, item = "strengths", {
            "title": title,
            "detail": detail,
            "paths": list(paths or []),
        }
    else:  # validation
        field, item = "validation_baseline", {
            "check": check,
            "command": command,
            "result": result,
            "details": details,
        }

    current = list(getattr(node, field) or [])
    current.append(item)
    setattr(node, field, current)
    node.updated_at = datetime.now(UTC)
    await node.save()
    return {"analysis_uid": node.uid, "note_type": note_type, "count": len(current)}
