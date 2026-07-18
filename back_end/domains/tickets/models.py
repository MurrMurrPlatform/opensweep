"""Ticket — unit of plannable work (PLATFORM_V2_DESIGN.md §3, §15 Phase 2).

Replaces the Linear issue. Gate-1 is the backlog → todo transition: nothing
implements without a human (maintainer+) approving. Findings link in via
`linked_finding_uids` (defer/promote), PRs via `linked_pr_uids`; a merged
linked PR completes the ticket (done via merge).
"""

from neomodel import (
    AsyncStructuredNode,
    DateTimeProperty,
    JSONProperty,
    StringProperty,
)


class Ticket(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)
    repository_uid = StringProperty(required=True, index=True)

    title = StringProperty(required=True)
    description = StringProperty(default="")
    acceptance_criteria = JSONProperty(default=[])
    labels = JSONProperty(default=[])

    status = StringProperty(default="backlog", index=True)
    # backlog | todo | in-progress | in-review | done  (Gate 1 = backlog → todo)
    priority = StringProperty(default="medium")  # low | medium | high | urgent
    size = StringProperty(default="")  # trivial | small | medium | large

    origin = StringProperty(default="human", index=True)  # finding | human | agent-proposal
    origin_finding_uid = StringProperty(default="", index=True)
    parent_ticket_uid = StringProperty(default="", index=True)

    # Cross-links to the discovery loop (findings) and delivery loop (PRs).
    linked_finding_uids = JSONProperty(default=[])
    linked_pr_uids = JSONProperty(default=[])

    assignee_uid = StringProperty(default="", index=True)

    # Implementation plan, written by the ticket's Thread (unified dev flow):
    # {markdown, state (drafted|approved), thread_uid, updated_at,
    #  approved_by, approved_at}. Empty dict = no plan yet.
    plan = JSONProperty(default={})

    # Gate-1 provenance — set on backlog → todo, kept as the approval record.
    approved_by = StringProperty(default="")
    approved_at = DateTimeProperty()

    done_at = DateTimeProperty()

    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)


class TicketGroupProposal(AsyncStructuredNode):
    """An agent-proposed batch of related tickets (PLATFORM_V2_DESIGN.md §15).

    Agents may only PROPOSE groupings — approval is human-only, mirroring
    Gate 1. Approving creates a parent Ticket (origin agent-proposal, born in
    backlog) and re-parents the members under it; rejecting just records the
    verdict. The member tickets themselves are never touched by a proposal.
    """

    uid = StringProperty(unique_index=True, required=True)
    repository_uid = StringProperty(required=True, index=True)

    title = StringProperty(required=True)  # title for the parent ticket on approval
    rationale = StringProperty(default="")  # why these belong in one batch
    member_ticket_uids = JSONProperty(default=[])
    suggested_labels = JSONProperty(default=[])
    suggested_priority = StringProperty(default="medium")

    status = StringProperty(default="proposed", index=True)  # proposed | approved | rejected
    source_run_uid = StringProperty(default="", index=True)  # run that proposed it

    # Review record — set on approve/reject; created_ticket_uid is the parent
    # ticket materialized by approval.
    created_ticket_uid = StringProperty(default="")
    reviewed_by = StringProperty(default="")
    reviewed_at = DateTimeProperty()

    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)


TICKET_STATUSES = {"backlog", "todo", "in-progress", "in-review", "done"}

TICKET_ORIGINS = {"finding", "human", "agent-proposal"}

TICKET_PRIORITIES = {"low", "medium", "high", "urgent"}

GROUP_PROPOSAL_STATUSES = {"proposed", "approved", "rejected"}
