"""Platform tool: create_finding."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import HTTPException

from domains.findings.models import Finding
from domains.findings.schemas import (
    Effort,
    FindingKind,
    FindingStatus,
    ParseStatus,
    Severity,
    SourcePath,
    normalize_tags,
)
from domains.findings.services.dedupe import build_dedupe_key
from infrastructure.audit import write_audit


def _enum_member(enum_cls, value: str, field: str):
    try:
        return enum_cls(value)
    except ValueError:
        expected = [member.value for member in enum_cls]
        raise HTTPException(
            status_code=422,
            detail=f"invalid {field}={value!r}; expected one of {expected}",
        ) from None


async def create_finding(
    *,
    repository_uid: str,
    title: str,
    tags: Optional[list[str]] = None,
    kind: str = "defect",
    severity: str = "medium",
    effort: str = "medium",
    subtype: str = "",
    confidence: float = 0.7,
    description: str = "",
    root_cause: str = "",
    why_it_matters: str = "",
    evidence: Optional[dict[str, Any]] = None,
    suggested_fix: str = "",
    affected_paths: Optional[list[str]] = None,
    detected_by_tool: str = "",
    detected_by_rule: str = "",
    source_run_uid: Optional[str] = None,
    executor: str = "manual",
    source_path: str = "tool-call",
    parse_status: str = "ok",
) -> dict[str, Any]:
    """Create a Finding and return its UID and dedupe key.

    `tags` are optional free-text labels ("security", "flaky-test", …) used
    for filtering — never a required taxonomy.

    The narrative fields (`description`, `root_cause`, `why_it_matters`,
    `suggested_fix`) are rendered to humans as markdown.

    `detected_by_tool`/`detected_by_rule` record static-analysis provenance:
    set them (to the candidate's tool + rule id) when this finding was filed
    after investigating a deterministic analyzer candidate; leave them empty
    for a finding the agent discovered on its own.

    Idempotent: a second call with the same (repo, title, top_path) updates
    the existing Finding's evidence + confidence instead of duplicating.
    """
    kind_member = _enum_member(FindingKind, kind, "kind")
    severity_member = _enum_member(Severity, severity, "severity")
    effort_member = _enum_member(Effort, effort, "effort")
    source_path_member = _enum_member(SourcePath, source_path, "source_path")
    parse_status_member = _enum_member(ParseStatus, parse_status, "parse_status")
    clean_tags = normalize_tags(tags)

    paths = list(affected_paths or [])
    dedupe = build_dedupe_key(
        repository_uid=repository_uid,
        title=title,
        top_path=paths[0] if paths else "",
    )
    existing = await Finding.nodes.get_or_none(dedupe_key=dedupe)
    if existing is not None:
        existing.confidence = max(float(existing.confidence or 0.0), float(confidence))
        existing.evidence = {**(existing.evidence or {}), **(evidence or {})}
        merged_tags = normalize_tags([*(existing.tags or []), *clean_tags])
        existing.tags = merged_tags
        # Narrative fields only fill gaps on merge — never overwrite a
        # richer earlier analysis with a re-filed duplicate's text.
        if description and not (existing.description or "").strip():
            existing.description = description
        if root_cause and not (existing.root_cause or "").strip():
            existing.root_cause = root_cause
        if why_it_matters and not (existing.why_it_matters or "").strip():
            existing.why_it_matters = why_it_matters
        if suggested_fix and not (existing.suggested_fix or "").strip():
            existing.suggested_fix = suggested_fix
        # Attribute the earliest tool that surfaced it — only fill a gap, never
        # relabel a finding already credited to an analyzer.
        if detected_by_tool and not (existing.detected_by_tool or "").strip():
            existing.detected_by_tool = detected_by_tool
            existing.detected_by_rule = detected_by_rule
        if source_run_uid:
            existing.source_run_uid = source_run_uid
        existing.updated_at = datetime.now(timezone.utc)
        await existing.save()
        return {"finding_uid": existing.uid, "dedupe_key": dedupe, "deduplicated": True}

    f = Finding(
        uid=uuid4().hex,
        repository_uid=repository_uid,
        tags=clean_tags,
        kind=kind_member.value,
        severity=severity_member.value,
        effort=effort_member.value,
        subtype=subtype or "",
        title=title,
        confidence=float(confidence),
        description=description,
        root_cause=root_cause,
        why_it_matters=why_it_matters,
        evidence=evidence or {},
        suggested_fix=suggested_fix,
        affected_paths=paths,
        dedupe_key=dedupe,
        detected_by_tool=detected_by_tool or "",
        detected_by_rule=detected_by_rule or "",
        source_run_uid=source_run_uid,
        executor=executor,
        source_path=source_path_member.value,
        parse_status=parse_status_member.value,
        status=FindingStatus.OPEN.value,
    )
    await f.save()
    await write_audit(
        kind="finding.filed",
        subject_uid=f.uid,
        subject_type="Finding",
        actor_uid=executor,
        payload={
            "tags": list(f.tags or []),
            "kind": f.kind,
            "severity": f.severity,
            "source_run_uid": f.source_run_uid,
            "detected_by_tool": f.detected_by_tool or "",
        },
    )
    return {"finding_uid": f.uid, "dedupe_key": dedupe, "deduplicated": False}
