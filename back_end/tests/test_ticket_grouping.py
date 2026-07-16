"""Pure-function tests for ticket grouping — intent builder + DTO mapping."""

from api.v1.tickets import _build_group_proposal_intent
from domains.tickets.models import GROUP_PROPOSAL_STATUSES, TicketGroupProposal
from domains.tickets.schemas import GroupProposalStatus, TicketDTO, TicketStatus
from domains.tickets.services.ticket_group_service import proposal_to_dto


def _ticket(uid: str, *, title: str = "t", status: str = "backlog", description: str = "") -> TicketDTO:
    return TicketDTO(
        uid=uid,
        repository_uid="repo1",
        title=title,
        status=TicketStatus(status),
        description=description,
    )


def test_intent_lists_every_candidate_with_uid_and_title():
    tickets = [_ticket("aaa111", title="Fix auth bug"), _ticket("bbb222", title="Harden auth flow")]
    intent = _build_group_proposal_intent(tickets, "repo1")
    assert "aaa111" in intent and "Fix auth bug" in intent
    assert "bbb222" in intent and "Harden auth flow" in intent
    assert "Repository uid: repo1" in intent
    assert "opensweep_platform_propose_ticket_group" in intent


def test_intent_truncates_long_descriptions_and_flattens_newlines():
    long_desc = "line1\nline2 " + "x" * 500
    intent = _build_group_proposal_intent([_ticket("a", description=long_desc), _ticket("b")], "r")
    assert "\nline2" not in intent  # newlines flattened inside the excerpt
    assert "…" in intent
    assert "x" * 300 not in intent  # truncated well below the raw length


def test_intent_is_read_only_and_human_gated():
    intent = _build_group_proposal_intent([_ticket("a"), _ticket("b")], "r")
    assert "do not modify any code" in intent
    assert "human reviews every proposal" in intent


def test_proposal_to_dto_maps_all_fields():
    p = TicketGroupProposal(
        uid="p1",
        repository_uid="repo1",
        title="Batch: auth cleanup",
        rationale="same subsystem",
        member_ticket_uids=["a", "b"],
        suggested_labels=["auth"],
        suggested_priority="high",
        status="proposed",
        source_run_uid="run1",
    )
    dto = proposal_to_dto(p)
    assert dto.uid == "p1"
    assert dto.repository_uid == "repo1"
    assert dto.title == "Batch: auth cleanup"
    assert dto.rationale == "same subsystem"
    assert dto.member_ticket_uids == ["a", "b"]
    assert dto.suggested_labels == ["auth"]
    assert dto.suggested_priority == "high"
    assert dto.status == GroupProposalStatus.PROPOSED
    assert dto.source_run_uid == "run1"
    assert dto.created_ticket_uid == ""
    assert dto.reviewed_by == ""


def test_proposal_to_dto_defaults_empty_fields():
    p = TicketGroupProposal(uid="p2", repository_uid="r", title="t")
    dto = proposal_to_dto(p)
    assert dto.status == GroupProposalStatus.PROPOSED
    assert dto.member_ticket_uids == []
    assert dto.suggested_priority == "medium"


def test_group_proposal_statuses():
    assert GROUP_PROPOSAL_STATUSES == {"proposed", "approved", "rejected"}
