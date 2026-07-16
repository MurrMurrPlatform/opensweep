"""Platform tool: update_finding."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from domains.findings.models import Finding
from domains.findings.schemas import (
    Effort,
    FindingStatus,
    Severity,
)
from infrastructure.audit import write_audit

_CHANGEABLE_FIELDS = {
    "severity",
    "effort",
    "subtype",
    "title",
    "confidence",
    "description",
    "root_cause",
    "why_it_matters",
    "evidence",
    "suggested_fix",
    "affected_paths",
    "status",
}


def _enum_value(enum_cls, value: str, field: str) -> str:
    try:
        return enum_cls(value).value
    except ValueError:
        expected = [member.value for member in enum_cls]
        raise HTTPException(
            status_code=422,
            detail=f"invalid {field}={value!r}; expected one of {expected}",
        ) from None


async def update_finding(
    *,
    finding_uid: str,
    changes: dict[str, Any],
    actor: str = "manual",
) -> dict[str, Any]:
    """Update facets on an existing Finding.

    Unknown fields are rejected — Findings have a fixed faceted shape;
    free-form notes belong in `evidence`.
    """
    changes = dict(changes or {})
    f = await Finding.nodes.get_or_none(uid=finding_uid)
    if f is None:
        raise HTTPException(status_code=404, detail=f"Finding {finding_uid} not found")

    unknown = set(changes.keys()) - _CHANGEABLE_FIELDS
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"unknown finding fields: {sorted(unknown)}"
        )

    if "severity" in changes:
        changes["severity"] = _enum_value(Severity, changes["severity"], "severity")
    if "effort" in changes:
        changes["effort"] = _enum_value(Effort, changes["effort"], "effort")
    if "status" in changes:
        changes["status"] = _enum_value(FindingStatus, changes["status"], "status")
    if "evidence" in changes and isinstance(changes["evidence"], dict):
        changes["evidence"] = {**(f.evidence or {}), **changes["evidence"]}

    for k, v in changes.items():
        setattr(f, k, v)
    f.updated_at = datetime.now(UTC)
    await f.save()
    await write_audit(
        kind="finding.updated",
        subject_uid=f.uid,
        subject_type="Finding",
        actor_uid=actor,
        payload={"changed": sorted(changes.keys())},
    )
    # status/severity are convergence inputs for any PR that holds a
    # resolution of this finding — refresh those ledgers (best-effort).
    if "status" in changes or "severity" in changes:
        try:
            from domains.delivery.services.pull_request_service import (
                recompute_open_prs_for_finding,
            )

            await recompute_open_prs_for_finding(f.uid)
        except Exception:  # noqa: BLE001 — never fail the finding update
            from logging_config import logger

            logger.warning(
                f"post-update PR recompute failed for finding {f.uid}",
                extra={"tag": "delivery"},
                exc_info=True,
            )
    return {"finding_uid": f.uid, "updated": sorted(changes.keys())}
