"""Ticket group proposals — agent-suggested batches, human-approved.

Mirrors the Gate-1 contract: agents may only PROPOSE a grouping (via the
platform tool); a maintainer approves or rejects it. Approval materializes a
parent Ticket (origin agent-proposal, born in backlog) and re-parents the
member tickets under it; the members' own statuses are never touched.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException

from domains.tickets.models import TICKET_PRIORITIES, Ticket, TicketGroupProposal
from domains.tickets.schemas import GroupProposalStatus, TicketGroupProposalDTO
from domains.tickets.services.ticket_service import TicketService
from infrastructure.audit import write_audit


def proposal_to_dto(p: TicketGroupProposal) -> TicketGroupProposalDTO:
    return TicketGroupProposalDTO(
        uid=p.uid,
        repository_uid=p.repository_uid,
        title=p.title or "",
        rationale=p.rationale or "",
        member_ticket_uids=list(p.member_ticket_uids or []),
        suggested_labels=list(p.suggested_labels or []),
        suggested_priority=p.suggested_priority or "medium",
        status=GroupProposalStatus(p.status or "proposed"),
        source_run_uid=p.source_run_uid or "",
        created_ticket_uid=p.created_ticket_uid or "",
        reviewed_by=p.reviewed_by or "",
        reviewed_at=p.reviewed_at,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


class TicketGroupService:
    async def get_node(self, uid: str) -> TicketGroupProposal:
        p = await TicketGroupProposal.nodes.get_or_none(uid=uid)
        if p is None:
            raise HTTPException(status_code=404, detail=f"TicketGroupProposal {uid} not found")
        return p

    async def list(
        self, *, repository_uid: str | None = None, status: str | None = None
    ) -> list[TicketGroupProposalDTO]:
        filters: dict = {}
        if repository_uid:
            filters["repository_uid"] = repository_uid
        if status:
            filters["status"] = status
        nodes = await (
            TicketGroupProposal.nodes.filter(**filters)
            if filters
            else TicketGroupProposal.nodes.all()
        )
        out = [proposal_to_dto(p) for p in nodes]
        floor = datetime.min.replace(tzinfo=UTC)
        out.sort(key=lambda d: d.created_at or floor, reverse=True)
        return out

    async def propose(
        self,
        *,
        repository_uid: str,
        title: str,
        rationale: str = "",
        member_ticket_uids: list[str],
        suggested_labels: list[str] | None = None,
        suggested_priority: str = "medium",
        source_run_uid: str = "",
        actor_uid: str | None = None,
    ) -> tuple[TicketGroupProposal, bool]:
        """Record a grouping proposal. Idempotent on the member set: an open
        proposal for the same repository with the same members is returned
        instead of duplicated. Returns (proposal, deduplicated)."""
        members = await TicketService().validate_group_members(
            repository_uid, member_ticket_uids
        )
        member_uids = [m.uid for m in members]

        existing = await TicketGroupProposal.nodes.filter(
            repository_uid=repository_uid, status="proposed"
        )
        for p in existing:
            if set(p.member_ticket_uids or []) == set(member_uids):
                return p, True

        p = TicketGroupProposal(
            uid=uuid4().hex,
            repository_uid=repository_uid,
            title=title,
            rationale=rationale,
            member_ticket_uids=member_uids,
            suggested_labels=list(suggested_labels or []),
            # Agents send free text — clamp to the priority vocabulary.
            suggested_priority=(
                suggested_priority if suggested_priority in TICKET_PRIORITIES else "medium"
            ),
            status="proposed",
            source_run_uid=source_run_uid,
        )
        await p.save()
        await write_audit(
            kind="ticket_group.proposed",
            subject_uid=p.uid,
            subject_type="TicketGroupProposal",
            actor_uid=actor_uid,
            payload={
                "repository_uid": repository_uid,
                "title": title,
                "member_ticket_uids": member_uids,
                "source_run_uid": source_run_uid,
            },
        )
        return p, False

    async def approve(self, uid: str, *, actor_uid: str) -> TicketGroupProposalDTO:
        """Human approval: materialize the parent ticket and re-parent the
        members. Members that disappeared or finished since the proposal are
        dropped; if fewer than 2 remain the proposal is stale (409)."""
        p = await self.get_node(uid)
        if p.status != "proposed":
            raise HTTPException(status_code=409, detail=f"proposal is already {p.status}")

        alive: list[str] = []
        for member_uid in list(p.member_ticket_uids or []):
            t = await Ticket.nodes.get_or_none(uid=member_uid)
            if t is None or t.status == "done" or t.repository_uid != p.repository_uid:
                continue
            alive.append(member_uid)
        if len(alive) < 2:
            raise HTTPException(
                status_code=409,
                detail="proposal is stale — fewer than 2 member tickets are still open",
            )

        parent = await TicketService().group_tickets(
            repository_uid=p.repository_uid,
            title=p.title,
            description=p.rationale or "",
            member_ticket_uids=alive,
            labels=list(p.suggested_labels or []),
            priority=p.suggested_priority or "medium",
            origin="agent-proposal",
            actor_uid=actor_uid,
        )

        p.status = "approved"
        p.created_ticket_uid = parent.uid
        p.reviewed_by = actor_uid
        p.reviewed_at = datetime.now(UTC)
        p.updated_at = p.reviewed_at
        await p.save()
        await write_audit(
            kind="ticket_group.approved",
            subject_uid=p.uid,
            subject_type="TicketGroupProposal",
            actor_uid=actor_uid,
            payload={
                "created_ticket_uid": parent.uid,
                "member_ticket_uids": alive,
            },
        )
        return proposal_to_dto(p)

    async def reject(self, uid: str, *, actor_uid: str) -> TicketGroupProposalDTO:
        p = await self.get_node(uid)
        if p.status != "proposed":
            raise HTTPException(status_code=409, detail=f"proposal is already {p.status}")
        p.status = "rejected"
        p.reviewed_by = actor_uid
        p.reviewed_at = datetime.now(UTC)
        p.updated_at = p.reviewed_at
        await p.save()
        await write_audit(
            kind="ticket_group.rejected",
            subject_uid=p.uid,
            subject_type="TicketGroupProposal",
            actor_uid=actor_uid,
            payload={},
        )
        return proposal_to_dto(p)
