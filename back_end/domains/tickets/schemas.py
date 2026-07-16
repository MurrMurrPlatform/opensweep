"""Ticket domain schemas — DTOs, enums, requests (PLATFORM_V2_DESIGN.md §3)."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TicketStatus(str, Enum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in-progress"
    IN_REVIEW = "in-review"
    DONE = "done"


class TicketDTO(BaseModel):
    uid: str
    repository_uid: str
    title: str
    description: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    status: TicketStatus = TicketStatus.BACKLOG
    priority: str = "medium"
    size: str = ""
    origin: str = "human"
    origin_finding_uid: str = ""
    parent_ticket_uid: str = ""
    linked_finding_uids: list[str] = Field(default_factory=list)
    linked_pr_uids: list[str] = Field(default_factory=list)
    assignee_uid: str = ""
    approved_by: str = ""
    approved_at: datetime | None = None
    done_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TicketDetailDTO(TicketDTO):
    """Ticket + its subtickets."""

    children: list[TicketDTO] = Field(default_factory=list)


# ── Requests ─────────────────────────────────────────────────────────────────


class CreateTicketRequest(BaseModel):
    title: str = Field(min_length=1)
    repository_uid: str = Field(min_length=1)
    description: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    priority: str = "medium"
    size: str = ""
    origin: str = "human"
    origin_finding_uid: str = ""
    parent_ticket_uid: str = ""
    assignee_uid: str = ""


class UpdateTicketRequest(BaseModel):
    """Field updates only — status moves exclusively through the transition
    endpoint so every move is legality-checked and audited."""

    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    acceptance_criteria: list[str] | None = None
    labels: list[str] | None = None
    priority: str | None = None
    size: str | None = None
    parent_ticket_uid: str | None = None
    assignee_uid: str | None = None


class TransitionTicketRequest(BaseModel):
    status: TicketStatus


class LinkFindingRequest(BaseModel):
    finding_uid: str = Field(min_length=1)


class LinkPullRequestRequest(BaseModel):
    pull_request_uid: str = Field(min_length=1)


# ── Grouping (parent/subtickets as one implementable batch) ──────────────────


class GroupTicketsRequest(BaseModel):
    """Group ≥2 existing tickets under a new parent ticket."""

    repository_uid: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    member_ticket_uids: list[str] = Field(min_length=2)
    labels: list[str] = Field(default_factory=list)
    priority: str = "medium"


class GroupProposalStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class TicketGroupProposalDTO(BaseModel):
    uid: str
    repository_uid: str
    title: str
    rationale: str = ""
    member_ticket_uids: list[str] = Field(default_factory=list)
    suggested_labels: list[str] = Field(default_factory=list)
    suggested_priority: str = "medium"
    status: GroupProposalStatus = GroupProposalStatus.PROPOSED
    source_run_uid: str = ""
    created_ticket_uid: str = ""
    reviewed_by: str = ""
    reviewed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
