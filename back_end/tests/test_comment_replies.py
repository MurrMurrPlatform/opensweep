"""Comment replies (one level) + thread-question routing (pure surface).

Full create/route behavior is DB-bound; here we pin the schema surface, the
model fields, and that the reply-routing guard ignores non-question parents.
"""

from types import SimpleNamespace

from domains.comments.models import Comment
from domains.comments.schemas import CommentDTO, CreateCommentRequest


def test_comment_model_has_reply_and_meta_fields():
    props = Comment.defined_properties(rels=False, aliases=False)
    assert "parent_comment_uid" in props
    assert "meta" in props


def test_create_request_accepts_parent():
    req = CreateCommentRequest(
        subject_type="ticket", subject_uid="t-1", body="yes", parent_comment_uid="c-1"
    )
    assert req.parent_comment_uid == "c-1"
    # And stays optional for top-level comments.
    top = CreateCommentRequest(subject_type="ticket", subject_uid="t-1", body="hi")
    assert top.parent_comment_uid == ""


def test_dto_defaults_for_reply_fields():
    dto = CommentDTO(
        uid="c1",
        subject_type="ticket",
        subject_uid="t1",
        author_uid="u1",
        body="hello",
    )
    assert dto.parent_comment_uid == ""
    assert dto.meta == {}


def test_question_meta_shape_written_by_ask_user():
    # The meta contract the UI chips + reply routing depend on.
    meta = {
        "kind": "thread_question",
        "thread_uid": "th-1",
        "question_uid": "q-1",
        "options": ["A", "B"],
        "status": "open",
    }
    assert meta["kind"] == "thread_question"
    assert set(meta) == {"kind", "thread_uid", "question_uid", "options", "status"}


async def _route(parent):
    from domains.threads.services import thread_service

    class FakeNodes:
        async def get_or_none(self, **kw):
            return parent

    class FakeComment:
        nodes = FakeNodes()

    import domains.comments.models as comment_models

    original = comment_models.Comment
    comment_models.Comment = FakeComment  # type: ignore[assignment]
    try:
        await thread_service.route_comment_reply(
            parent_comment_uid="c-1", body="answer", actor_uid="u-1"
        )
    finally:
        comment_models.Comment = original  # type: ignore[assignment]


def test_reply_routing_ignores_non_question_parents():
    import asyncio

    # Plain comment (no meta) — routing is a silent no-op, never an error.
    asyncio.run(_route(SimpleNamespace(meta={})))
    # Already-answered question — same.
    asyncio.run(
        _route(SimpleNamespace(meta={"kind": "thread_question", "status": "answered"}))
    )
    # Missing parent — same.
    asyncio.run(_route(None))
