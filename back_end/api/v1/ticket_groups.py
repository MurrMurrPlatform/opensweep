"""Ticket group proposal routes — list, approve, reject.

Agents propose groupings through the platform tool surface
(`opensweep_platform_propose_ticket_group`); humans review them here. Approval
materializes the parent ticket and re-parents the members — mirroring the
Gate-1 contract, agents can never apply their own groupings.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_current_user, require_role
from domains.tenancy import org_repo_uids, require_repo_in_org
from domains.tickets.models import GROUP_PROPOSAL_STATUSES
from domains.tickets.schemas import TicketGroupProposalDTO
from domains.tickets.services.ticket_group_service import TicketGroupService
from domains.users.schemas import UserDTO

router = APIRouter(prefix="/api/v1/ticket-group-proposals", tags=["tickets"])


@router.get(
    "",
    response_model=list[TicketGroupProposalDTO],
    operation_id="opensweep_ticket_group_proposal_list",
)
async def list_group_proposals(
    repository_uid: str | None = Query(None),
    status: str | None = Query(None),
    user: UserDTO = Depends(get_current_user),
):
    if status is not None and status not in GROUP_PROPOSAL_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {sorted(GROUP_PROPOSAL_STATUSES)}",
        )
    if repository_uid is not None:
        await require_repo_in_org(repository_uid, user.org_uid)
    items = await TicketGroupService().list(repository_uid=repository_uid, status=status)
    if repository_uid is None:
        allowed = await org_repo_uids(user.org_uid)
        items = [p for p in items if p.repository_uid in allowed]
    return items


@router.post(
    "/{uid}/approve",
    response_model=TicketGroupProposalDTO,
    operation_id="opensweep_ticket_group_proposal_approve",
)
async def approve_group_proposal(
    uid: str, user: UserDTO = Depends(require_role("maintainer"))
):
    """Approve: creates the parent ticket (origin agent-proposal, backlog) and
    re-parents the still-open members under it. 409 if already reviewed or
    fewer than 2 members remain open."""
    service = TicketGroupService()
    proposal = await service.get_node(uid)
    await require_repo_in_org(proposal.repository_uid, user.org_uid)
    return await service.approve(uid, actor_uid=user.uid)


@router.post(
    "/{uid}/reject",
    response_model=TicketGroupProposalDTO,
    operation_id="opensweep_ticket_group_proposal_reject",
)
async def reject_group_proposal(
    uid: str, user: UserDTO = Depends(require_role("maintainer"))
):
    service = TicketGroupService()
    proposal = await service.get_node(uid)
    await require_repo_in_org(proposal.repository_uid, user.org_uid)
    return await service.reject(uid, actor_uid=user.uid)
