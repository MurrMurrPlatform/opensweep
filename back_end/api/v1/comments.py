"""Comment routes — discussion threads on any OpenSweep data item.

Any authenticated user may comment; deletion is author-or-admin. Bodies may
mention @opensweep (dispatches a background run that answers in-thread) and other
data items via `@[Label](type:uid)` tokens. Agents read threads through
`opensweep_platform_list_comments` and reply through `opensweep_platform_add_comment`.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from api.dependencies import get_current_user
from domains.comments import mentions as mention_lib
from domains.comments import service as comment_service
from domains.comments.opensweep_mention import pending_opensweep_runs, trigger_opensweep_reply
from domains.comments.models import Comment
from domains.comments.schemas import (
    CommentDTO,
    CommentSubjectType,
    CreateCommentRequest,
    PendingOpenSweepRunDTO,
)
from domains.comments.subjects import get_subject
from domains.tenancy import require_repo_in_org
from domains.users.schemas import UserDTO, role_at_least
from infrastructure.audit import write_audit

router = APIRouter(prefix="/api/v1/comments", tags=["comments"])

# Re-exported for the platform-tool transport.
list_comments_for = comment_service.list_comments_for


@router.get("", response_model=list[CommentDTO], operation_id="opensweep_comment_list")
async def list_comments(
    subject_type: CommentSubjectType = Query(...),
    subject_uid: str = Query(..., min_length=1),
    user: UserDTO = Depends(get_current_user),
):
    subject = await get_subject(subject_type, subject_uid)
    repo_uid = subject.repository_uid if subject is not None else None
    await require_repo_in_org(repo_uid, user.org_uid)
    return await comment_service.list_comments_for(subject_type, subject_uid)


@router.get(
    "/pending-opensweep-runs",
    response_model=list[PendingOpenSweepRunDTO],
    operation_id="opensweep_comment_pending_runs",
)
async def list_pending_opensweep_runs(
    subject_type: CommentSubjectType = Query(...),
    subject_uid: str = Query(..., min_length=1),
    user: UserDTO = Depends(get_current_user),
):
    """In-flight @opensweep reply runs for a thread, so the thinking bubble
    survives a page reload."""
    subject = await get_subject(subject_type, subject_uid)
    repo_uid = subject.repository_uid if subject is not None else None
    await require_repo_in_org(repo_uid, user.org_uid)
    runs = await pending_opensweep_runs(subject_type, subject_uid)
    return [
        PendingOpenSweepRunDTO(
            run_uid=r.uid,
            comment_uid=str((r.target or {}).get("comment_uid") or ""),
            status=r.status or "",
            started_at=r.started_at,
        )
        for r in runs
    ]


@router.post("", response_model=CommentDTO, operation_id="opensweep_comment_create")
async def create_comment(
    req: CreateCommentRequest, user: UserDTO = Depends(get_current_user)
):
    """Any authenticated user may comment; the subject must exist in their org.

    An @opensweep mention in the body dispatches a background run that reads the
    thread, acts, and replies — its uid comes back as `triggered_run_uid`."""
    subject = await get_subject(req.subject_type, req.subject_uid)
    if subject is None:
        raise HTTPException(
            status_code=404,
            detail=f"{req.subject_type.value} {req.subject_uid} not found",
        )
    await require_repo_in_org(subject.repository_uid, user.org_uid)
    c = await comment_service.create_comment(
        subject_type=req.subject_type,
        subject_uid=req.subject_uid,
        body=req.body,
        author_uid=user.uid,
    )
    dto = await comment_service.comment_to_dto(c)
    if mention_lib.mentions_opensweep(req.body):
        dto.triggered_run_uid = await trigger_opensweep_reply(c, req.subject_type, subject)
    return dto


@router.delete("/{uid}", status_code=204, operation_id="opensweep_comment_delete")
async def delete_comment(uid: str, user: UserDTO = Depends(get_current_user)):
    """Author-or-admin only."""
    c = await Comment.nodes.get_or_none(uid=uid)
    if c is None:
        raise HTTPException(status_code=404, detail=f"Comment {uid} not found")
    subject = await get_subject(CommentSubjectType(c.subject_type), c.subject_uid)
    repo_uid = subject.repository_uid if subject is not None else None
    await require_repo_in_org(repo_uid, user.org_uid)
    if c.author_uid != user.uid and not role_at_least(user.role, "admin"):
        raise HTTPException(
            status_code=403, detail="only the author or an admin may delete a comment"
        )
    await write_audit(
        kind="comment.deleted",
        subject_uid=c.uid,
        subject_type="Comment",
        actor_uid=user.uid,
        payload={
            "comment_subject_type": c.subject_type,
            "comment_subject_uid": c.subject_uid,
        },
    )
    await c.delete()
    return Response(status_code=204)
