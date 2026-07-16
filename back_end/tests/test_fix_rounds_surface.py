"""Fix-round accounting surface — reset route mounted, exhaustion exposed on
the DTO, and the counter denormalization helper behaves.
"""

from app import app
from domains.delivery.models import PullRequest
from domains.delivery.services.pull_request_service import pull_request_to_dto
from domains.delivery.services.write_gate import fix_rounds_exhausted


def _openapi_operation_ids() -> set[str]:
    schema = app.openapi()
    ops = set()
    for methods in schema.get("paths", {}).values():
        for op in methods.values():
            if isinstance(op, dict) and op.get("operationId"):
                ops.add(op["operationId"])
    return ops


def test_reset_fix_rounds_route_mounted():
    assert "opensweep_reset_fix_rounds" in _openapi_operation_ids()
    paths = set(app.openapi().get("paths", {}).keys())
    assert "/api/v1/delivery/pull-requests/{uid}/reset-fix-rounds" in paths


def test_pull_request_dto_exposes_fix_rounds_exhausted():
    props = app.openapi()["components"]["schemas"]["PullRequestDTO"]["properties"]
    assert "fix_rounds_exhausted" in props


def test_dto_carries_the_denormalized_flag():
    pr = PullRequest(
        uid="p1",
        repository_uid="r1",
        github_number=7,
        pr_key="r1:7",
        fix_rounds=2,
        fix_rounds_exhausted=True,
    )
    dto = pull_request_to_dto(pr)
    assert dto.fix_rounds == 2
    assert dto.fix_rounds_exhausted is True

    fresh = PullRequest(uid="p2", repository_uid="r1", github_number=8, pr_key="r1:8")
    assert pull_request_to_dto(fresh).fix_rounds_exhausted is False


def test_exhaustion_predicate_semantics():
    assert fix_rounds_exhausted(2, 2)
    assert fix_rounds_exhausted(3, 2)
    assert not fix_rounds_exhausted(1, 2)
    assert not fix_rounds_exhausted(0, 2)
