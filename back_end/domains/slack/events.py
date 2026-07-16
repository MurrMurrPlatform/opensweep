"""Slack notification event catalog — the user-facing event types tenants can
route to channels, and the mapping from internal audit kinds onto them.

The audit stream (infrastructure/audit.write_audit) is the single choke point
every interesting state transition already flows through, so Slack delivery
subscribes there instead of instrumenting call sites. A rule stores one
`event_type` from CATALOG; `event_types_for` translates an audit kind (+
payload) into the matching event types at delivery time.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationEvent:
    event_type: str
    label: str
    description: str
    emoji: str  # Slack emoji shortcode, without colons


CATALOG: tuple[NotificationEvent, ...] = (
    NotificationEvent(
        "run.completed",
        "Run completed",
        "An agent run finished (any playbook: ask, review, fix, implement, verify, document).",
        "white_check_mark",
    ),
    NotificationEvent(
        "run.failed",
        "Run failed",
        "An agent run errored — dispatch failure, executor crash, or workspace prep failure.",
        "x",
    ),
    NotificationEvent(
        "attention.required",
        "Human attention required",
        "OpenSweep needs a human: a review verdict came back needs-human, a "
        "verification could not conclude, or a run is paused on provider quota.",
        "rotating_light",
    ),
    NotificationEvent(
        "ticket.created",
        "Ticket created",
        "A new ticket was filed (by a human, from a finding, or generated).",
        "ticket",
    ),
    NotificationEvent(
        "ticket.status_changed",
        "Ticket status changed",
        "A ticket moved between board lanes, including auto-completion when its PR merged.",
        "arrows_counterclockwise",
    ),
    NotificationEvent(
        "finding.created",
        "New finding",
        "An analysis or review filed a new finding.",
        "mag",
    ),
    NotificationEvent(
        "finding.resolved",
        "Finding fixed",
        "A finding was marked fixed.",
        "hammer_and_wrench",
    ),
    NotificationEvent(
        "pr.opened",
        "Pull request opened",
        "OpenSweep opened a draft PR from an implement run.",
        "seedling",
    ),
    NotificationEvent(
        "review.completed",
        "Review completed",
        "A PR review verdict was submitted (approve / request changes / needs human).",
        "clipboard",
    ),
    NotificationEvent(
        "fix.pushed",
        "Fix pushed",
        "A fix run pushed a commit onto a PR branch.",
        "wrench",
    ),
    NotificationEvent(
        "analysis.completed",
        "Analysis completed",
        "A sweep finished: audit, deep scan, or documentation generation.",
        "bar_chart",
    ),
    NotificationEvent(
        "docs.exported",
        "Docs exported",
        "The documentation tree was exported (AGENTS.md PR).",
        "books",
    ),
    NotificationEvent(
        "news.filed",
        "News item filed",
        "The news scout filed an item matching the org's interests.",
        "newspaper",
    ),
    NotificationEvent(
        "repository.registered",
        "Repository registered",
        "A repository was linked to OpenSweep.",
        "package",
    ),
    NotificationEvent(
        "comment.created",
        "Comment posted",
        "Someone (or OpenSweep) commented on a finding, ticket, or pull request.",
        "speech_balloon",
    ),
)

EVENT_TYPES: frozenset[str] = frozenset(e.event_type for e in CATALOG)

BY_TYPE: dict[str, NotificationEvent] = {e.event_type: e for e in CATALOG}

# audit kind → notification event type(s). Kinds absent here never reach the
# delivery task (write_audit pre-filters on RELEVANT_AUDIT_KINDS).
_KIND_MAP: dict[str, tuple[str, ...]] = {
    "run.ended": ("run.completed",),
    "run.failed": ("run.failed",),
    "run.paused_quota": ("attention.required",),
    "verification.needs_human": ("attention.required",),
    "ticket.created": ("ticket.created",),
    "ticket.transitioned": ("ticket.status_changed",),
    "ticket.done_via_merge": ("ticket.status_changed",),
    "finding.filed": ("finding.created",),
    "finding.fixed": ("finding.resolved",),
    "implement_run.pr_opened": ("pr.opened",),
    "verdict.submitted": ("review.completed",),
    "fix_run.pushed": ("fix.pushed",),
    "sweep.audit_completed": ("analysis.completed",),
    "sweep.auto_audit_completed": ("analysis.completed",),
    "sweep.deep_scan_completed": ("analysis.completed",),
    "sweep.generate_docs_completed": ("analysis.completed",),
    "docs.exported": ("docs.exported",),
    "news.filed": ("news.filed",),
    "repository.registered": ("repository.registered",),
    "comment.created": ("comment.created",),
}

RELEVANT_AUDIT_KINDS: frozenset[str] = frozenset(_KIND_MAP)


def event_types_for(kind: str, payload: dict | None = None) -> list[str]:
    """The notification event types an audit event maps onto (possibly none)."""
    types = list(_KIND_MAP.get(kind, ()))
    payload = payload or {}
    # A needs-human review verdict is both "review completed" and a call for
    # a human — orgs routing only attention.required must still see it.
    if kind == "verdict.submitted" and payload.get("result") == "needs_human":
        types.append("attention.required")
    return types
