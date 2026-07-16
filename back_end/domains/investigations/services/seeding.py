"""Per-repository seeded Investigations.

Every repository gets one on-event "Keep docs current" Investigation on
registration (KNOWLEDGE_V3_DOCUMENTATION.md §9): a document run, eligible
whenever a push lands, gated by its compute_dial (default `suggest` — the
user dials it up to auto-run-cheap/any to make every push refresh the
wiki). Empty target = repo-wide, so any change makes it a candidate.
"""

from __future__ import annotations

from uuid import uuid4

from domains.investigations.models import Investigation
from domains.investigations.schemas import ExecutionMode, InvestigationProvenance

KEEP_DOCS_CURRENT_TITLE = "Keep docs current"


async def seed_keep_docs_current_investigation(
    repository_uid: str,
) -> Investigation | None:
    """Idempotent: one seeded docs-freshness Investigation per repository."""
    for i in await Investigation.nodes.all():
        if (
            i.repository_uid == repository_uid
            and i.title == KEEP_DOCS_CURRENT_TITLE
            and i.job_type == "document"
        ):
            return None
    inv = Investigation(
        uid=uuid4().hex,
        repository_uid=repository_uid,
        intent=(
            "Code changed since the documentation was last reviewed. Compare the "
            "stale Documentation pages (list_docs shows which) and Memories "
            "against the current code: propose_doc_edit where pages are wrong, "
            "confirm_doc_current where they still hold, rewrite invalidated "
            "memories via write_memory. Prefer deleting stale prose over adding "
            "new prose."
        ),
        job_type="document",
        target={},
        effort="normal",
        default_mode=ExecutionMode.ANALYZE_ONLY.value,
        provenance=InvestigationProvenance.TEMPLATE.value,
        schedule="on-event",
        compute_dial="suggest",
        title=KEEP_DOCS_CURRENT_TITLE,
    )
    await inv.save()
    return inv


AUDIT_STALE_TITLE = "Audit stale code"


async def seed_audit_stale_investigation(repository_uid: str) -> Investigation | None:
    """Idempotent: one seeded staleness-audit Investigation per repository.

    Seeded INERT (schedule="") — a user-set cron is the opt-in, matching the
    scanner's semantics. Each due tick runs sweep.run_auto_audit: rank pages
    never-checked first then longest-stale, dispatch one scoped audit per
    page up to target.limit."""
    for i in await Investigation.nodes.all():
        if (
            i.repository_uid == repository_uid
            and i.title == AUDIT_STALE_TITLE
            and i.job_type == "audit-stale"
        ):
            return None
    inv = Investigation(
        uid=uuid4().hex,
        repository_uid=repository_uid,
        intent=(
            "Automatically audit the stalest / never-checked documentation pages: "
            "each due tick selects up to target.limit pages (never-checked first, "
            "then longest-stale) and dispatches one audit run scoped to each "
            "page's watch_paths."
        ),
        job_type="audit-stale",
        target={"limit": 3},
        effort="normal",
        default_mode=ExecutionMode.ANALYZE_ONLY.value,
        provenance=InvestigationProvenance.TEMPLATE.value,
        schedule="",
        compute_dial="ask-before-run",
        title=AUDIT_STALE_TITLE,
    )
    await inv.save()
    return inv
