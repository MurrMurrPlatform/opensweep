"""FindingKind.FEATURE_IDEA — schema round-trip + metrics exclusion pins.

feature-idea findings live on the Ideas board, not the quality metrics:
_REAL_FINDING_KINDS must keep excluding them (like proposals) so the
health numbers never count product ideas as code problems.
"""

from domains.findings.models import FINDING_KINDS
from domains.findings.schemas import FileFindingRequest, FindingKind
from domains.metrics.services.metrics_service import _REAL_FINDING_KINDS


def test_feature_idea_round_trips_through_the_enum():
    kind = FindingKind("feature-idea")
    assert kind is FindingKind.FEATURE_IDEA
    assert kind.value == "feature-idea"


def test_feature_idea_in_model_kinds():
    assert "feature-idea" in FINDING_KINDS


def test_feature_idea_excluded_from_real_finding_metrics():
    assert "feature-idea" not in _REAL_FINDING_KINDS


def test_file_finding_request_accepts_feature_idea():
    req = FileFindingRequest(kind="feature-idea", repository_uid="r", title="t")
    assert req.kind is FindingKind.FEATURE_IDEA
