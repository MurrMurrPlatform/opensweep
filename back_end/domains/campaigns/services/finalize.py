"""Campaign finalize: fold the parts' outcomes into one digest.

`build_summary` is pure (counts + coverage + holes); `finalize_campaign`
loads each part's findings (source_run_uid / source_run_uids match) and
Checked coverage stamps, saves the summary, and closes the campaign —
done, or failed when EVERY part failed. Idempotent: the tick re-runs it
for rows stranded in finalizing by a crash.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from infrastructure.audit import write_audit
from logging_config import logger


def build_summary(
    parts: list[dict],
    findings_by_part: dict[int, list[dict]],
    holes: list[str],
) -> dict:
    """The campaign digest. Pure.

    `findings_by_part` maps part idx → [{severity, tags, title}]; parts may
    carry `covered`/`skipped` counts (from their Checked stamps). `holes`
    are the scope paths of failed/never-run parts — the coverage debt this
    campaign leaves behind.
    """
    by_severity: Counter[str] = Counter()
    by_part: dict[int, int] = {}
    for idx, findings in findings_by_part.items():
        by_part[int(idx)] = len(findings)
        for f in findings:
            by_severity[str(f.get("severity") or "medium")] += 1
    return {
        "counts": {
            "by_severity": dict(by_severity),
            "by_part": {str(k): v for k, v in sorted(by_part.items())},
            "total": sum(by_part.values()),
        },
        "coverage": {
            "parts": [
                {
                    "idx": int(p["idx"]),
                    "title": p.get("title") or "",
                    "covered": int(p.get("covered") or 0),
                    "skipped": int(p.get("skipped") or 0),
                    "state": p.get("state") or "pending",
                }
                for p in sorted(parts, key=lambda p: int(p["idx"]))
            ],
            "holes": list(holes),
        },
        "failed_parts": sorted(
            int(p["idx"]) for p in parts if p.get("state") == "failed"
        ),
    }


async def finalize_campaign(campaign) -> None:
    """finalizing → done|failed, with the digest saved and audited."""
    from domains.campaigns.models import Campaign, is_legal_status_transition
    from domains.checked.models import Checked
    from domains.findings.models import Finding

    parts = [dict(p) for p in (campaign.parts or [])]
    run_by_idx = {int(p["idx"]): p.get("run_uid") or "" for p in parts}

    findings = list(await Finding.nodes.filter(repository_uid=campaign.repository_uid))
    findings_by_part: dict[int, list[dict]] = {}
    for idx, run_uid in run_by_idx.items():
        if not run_uid:
            continue
        matched = [
            f
            for f in findings
            if (f.source_run_uid or "") == run_uid or run_uid in (f.source_run_uids or [])
        ]
        if matched:
            findings_by_part[idx] = [
                {"severity": f.severity or "medium", "tags": list(f.tags or []), "title": f.title}
                for f in matched
            ]

    # Coverage counts from the runs' Checked stamps (complete_run contract).
    coverage_by_run: dict[str, tuple[int, int]] = {}
    try:
        for c in await Checked.nodes.filter(repository_uid=campaign.repository_uid):
            if c.run_uid in run_by_idx.values():
                coverage_by_run[c.run_uid] = (
                    len(c.covered_paths or []),
                    len(c.skipped_paths or []),
                )
    except Exception as exc:  # noqa: BLE001 — coverage counts are best-effort
        logger.warning(
            f"campaign {campaign.uid}: coverage stamps unavailable: {exc}",
            extra={"tag": "campaigns"},
        )
    for p in parts:
        covered, skipped = coverage_by_run.get(p.get("run_uid") or "", (0, 0))
        p["covered"] = covered
        p["skipped"] = skipped

    holes = [
        path
        for p in parts
        if p.get("state") != "done"
        for path in (p.get("scope_paths") or [])
    ]
    summary = build_summary(parts, findings_by_part, holes)

    all_failed = bool(parts) and all(p.get("state") == "failed" for p in parts)
    to_status = "failed" if all_failed else "done"

    fresh = await Campaign.nodes.get_or_none(uid=campaign.uid) or campaign
    if not is_legal_status_transition(fresh.status or "", to_status):
        return  # already finalized by a concurrent tick

    # Audit BEFORE the status save: the notification feed derives from the
    # audit stream, and a crash between save and audit would be unrecoverable
    # (done→done is illegal, so re-entry returns above without ever
    # auditing). The reverse crash merely re-audits once — the lesser evil.
    await write_audit(
        kind="campaign.failed" if all_failed else "campaign.completed",
        subject_uid=fresh.uid,
        subject_type="Campaign",
        repository_uid=fresh.repository_uid,
        actor_uid=fresh.created_by or "campaign",
        payload={
            "title": fresh.title or "",
            "counts": summary["counts"],
            "failed_parts": summary["failed_parts"],
        },
    )

    now = datetime.now(UTC)
    fresh.summary = summary
    fresh.status = to_status
    fresh.events = [
        *(fresh.events or []),
        {"ts": now.isoformat(), "type": "finalized", "status": to_status},
    ]
    fresh.updated_at = now
    await fresh.save()
