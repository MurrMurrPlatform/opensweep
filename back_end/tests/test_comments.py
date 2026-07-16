"""Comments — DTO/validation contract, mention parsing, route surface,
agent read/write tools, and the @opensweep summon intent."""

import pytest
from pydantic import ValidationError

from domains.comments import mentions as mention_lib
from domains.comments.models import COMMENT_SUBJECT_TYPES
from domains.comments.schemas import (
    CommentAuthorKind,
    CommentDTO,
    CommentSubjectType,
    CreateCommentRequest,
)

# ── schema contract ──────────────────────────────────────────────────────────


def test_subject_types_cover_every_data_item():
    assert COMMENT_SUBJECT_TYPES == {
        "finding",
        "ticket",
        "pull_request",
        "news_item",
        "run",
        "investigation",
        "doc",
    }
    assert {t.value for t in CommentSubjectType} == COMMENT_SUBJECT_TYPES


def test_create_request_requires_nonempty_body():
    with pytest.raises(ValidationError):
        CreateCommentRequest(subject_type="finding", subject_uid="f1", body="")


def test_create_request_requires_nonempty_subject_uid():
    with pytest.raises(ValidationError):
        CreateCommentRequest(subject_type="ticket", subject_uid="", body="do it")


def test_create_request_rejects_unknown_subject_type():
    with pytest.raises(ValidationError):
        CreateCommentRequest(subject_type="repository", subject_uid="r1", body="hi")


def test_comment_dto_shape():
    dto = CommentDTO(
        uid="c1",
        subject_type="pull_request",
        subject_uid="pr1",
        author_uid="local-user",
        author_name="Local User",
        body="waive the naming finding, it's intentional",
    )
    data = dto.model_dump()
    assert set(data) == {
        "uid",
        "subject_type",
        "subject_uid",
        "author_uid",
        "author_name",
        "author_kind",
        "source_run_uid",
        "body",
        "mentions",
        "triggered_run_uid",
        "created_at",
    }
    assert data["author_kind"] == CommentAuthorKind.USER
    assert data["mentions"] == []


# ── mention parsing ──────────────────────────────────────────────────────────


def test_opensweep_mention_detection():
    assert mention_lib.mentions_opensweep("@opensweep please refine this ticket")
    assert mention_lib.mentions_opensweep("hey @OpenSweep, group these")
    assert not mention_lib.mentions_opensweep("email me at hi@opensweepplatform.dev")
    assert not mention_lib.mentions_opensweep("@opensweeps are not summoned")
    assert not mention_lib.mentions_opensweep("no mention here")


def test_item_mention_parsing_dedupes_and_drops_unknown_types():
    body = (
        "@opensweep group @[Fix login](ticket:abc123) with "
        "@[Refactor Tickets](group:def456) and @[Fix login](ticket:abc123) "
        "but never @[bad](wizard:zzz)"
    )
    refs = mention_lib.parse_item_mentions(body)
    assert refs == [
        {"type": "ticket", "uid": "abc123", "label": "Fix login"},
        {"type": "group", "uid": "def456", "label": "Refactor Tickets"},
    ]


def test_plain_text_flattens_tokens_for_prompts():
    text = mention_lib.plain_text("see @[Fix login](ticket:abc123) for details")
    assert text == "see Fix login (ticket abc123) for details"


# ── @opensweep summon intent ─────────────────────────────────────────────────────


def test_opensweep_comment_intent_requires_a_reply():
    from domains.comments.opensweep_mention import build_opensweep_comment_intent
    from domains.comments.models import Comment
    from domains.tickets.models import Ticket

    ticket = Ticket(
        uid="t1",
        repository_uid="repo1",
        title="Fix login",
        description="d",
        status="backlog",
        priority="high",
    )
    comment = Comment(
        uid="c1",
        subject_type="ticket",
        subject_uid="t1",
        author_uid="u1",
        body="@opensweep please refine this ticket",
    )
    intent = build_opensweep_comment_intent(
        CommentSubjectType.TICKET, ticket, comment, thread="", mentioned=""
    )
    assert "opensweep_platform_add_comment" in intent
    assert "subject_uid='t1'" in intent
    assert "@opensweep please refine this ticket" in intent
    assert "read-only" in intent


# ── route surface ────────────────────────────────────────────────────────────


def _openapi():
    from app import app

    return app.openapi()


def test_comment_routes_are_mounted():
    schema = _openapi()
    paths = schema["paths"]
    assert "/api/v1/comments" in paths
    assert "/api/v1/comments/{uid}" in paths
    assert "/api/v1/mentions/search" in paths
    ops = {
        op.get("operationId")
        for methods in paths.values()
        for op in methods.values()
        if isinstance(op, dict)
    }
    for op_id in (
        "opensweep_comment_list",
        "opensweep_comment_create",
        "opensweep_comment_delete",
        "opensweep_mention_search",
        "opensweep_sync_repository_pull_requests",
    ):
        assert op_id in ops, f"missing operation {op_id}"


def test_agents_can_read_and_reply_on_threads():
    from mcp_app import OPENSWEEP_PLATFORM_TOOL_OPERATIONS

    ops = set(OPENSWEEP_PLATFORM_TOOL_OPERATIONS)
    assert "opensweep_platform_list_comments" in ops
    assert "opensweep_platform_add_comment" in ops


def test_platform_add_comment_route_is_mounted():
    schema = _openapi()
    path = "/api/v1/platform-tools/comments"
    assert path in schema["paths"]
    assert schema["paths"][path]["post"]["operationId"] == "opensweep_platform_add_comment"


def test_pull_request_sweep_is_scheduled():
    from celery_app import app as celery

    beat = celery.conf.beat_schedule
    assert beat["pull-request-sync"]["task"] == "opensweep.delivery.sync_pull_requests"


# ── intents tell agents to look ──────────────────────────────────────────────


def test_review_intent_mentions_the_comments_tool():
    from domains.delivery.models import PullRequest
    from domains.delivery.services.review_run_service import build_review_intent

    pr = PullRequest(
        uid="pr1",
        repository_uid="repo1",
        github_number=7,
        pr_key="repo1:7",
        title="t",
        head_sha="a" * 40,
        head_ref="feat/x",
        base_ref="main",
    )
    intent = build_review_intent(pr, {"default": "high"})
    assert "opensweep_platform_list_comments" in intent
    assert "human instructions" in intent


def test_fix_intent_mentions_the_comments_tool():
    from domains.delivery.models import PullRequest
    from domains.delivery.services.fix_run_service import build_fix_intent

    pr = PullRequest(
        uid="pr1",
        repository_uid="repo1",
        github_number=7,
        pr_key="repo1:7",
        title="t",
        head_ref="feat/x",
        base_ref="main",
    )
    intent = build_fix_intent(pr, [{"resolution_uid": "res1", "title": "bug"}], [])
    assert "opensweep_platform_list_comments" in intent
    assert "human instructions" in intent
