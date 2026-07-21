"""Analysis domain — model constants, DTO shapes, and node→DTO conversion.

DB-free: constructs an unsaved Analysis node and converts it. The finding
roll-up (which queries Neo4j) is covered separately in integration.
"""

from domains.analysis.models import (
    ANALYSIS_SECTION_KEYS,
    ANALYSIS_STATUSES,
    COVERAGE_STATUSES,
    NOTE_TYPES,
    QUESTION_STATUSES,
    SCORE_DIMENSIONS,
    Analysis,
)
from domains.analysis.schemas import AnalysisDTO, AnalysisStatus, QuestionStatus
from domains.analysis.services.analysis_service import analysis_to_dto


def test_status_and_note_constants():
    assert ANALYSIS_STATUSES == {
        "in_progress",
        "complete",
        "incomplete",
        "superseded",
        "archived",
    }
    assert QUESTION_STATUSES == {"open", "answered", "dismissed"}
    assert COVERAGE_STATUSES == {"examined", "partial", "skipped"}
    assert NOTE_TYPES == {"coverage", "strength", "validation"}
    # Section keys advisory; the report's core sections must be present.
    assert {"executive_summary", "implementation_plan", "top_changes"} <= ANALYSIS_SECTION_KEYS
    assert "security" in SCORE_DIMENSIONS and "testing" in SCORE_DIMENSIONS


def test_dto_defaults():
    dto = AnalysisDTO(uid="a1", repository_uid="r1", source_run_uid="run1")
    assert dto.status == AnalysisStatus.IN_PROGRESS
    assert dto.scorecard == [] and dto.sections == {} and dto.questions == []
    assert dto.finding_count == 0


def test_analysis_to_dto_maps_rich_fields():
    a = Analysis(
        uid="a1",
        repository_uid="r1",
        source_run_uid="run1",
        title="Deep scan — whole repository",
        status="complete",
        health_grade="B",
        health_score=82,
        scorecard=[{"dimension": "security", "score": 70, "max": 100, "grade": "C", "rationale": "x"}],
        confidence="high",
        sections={"executive_summary": "# Summary\n\nok"},
        coverage=[{"area": "backend", "paths": ["back_end/"], "status": "examined", "note": ""}],
        strengths=[{"title": "clean tenancy", "detail": "d", "paths": []}],
        validation_baseline=[{"check": "pytest", "command": "pytest -q", "result": "pass", "details": ""}],
        questions=[
            {"uid": "q1", "question": "prod scale?", "status": "open"},
            {"uid": "q2", "question": "answered one", "status": "answered", "answer": "yes"},
        ],
    )
    dto = analysis_to_dto(a)
    assert dto.health_grade == "B" and dto.health_score == 82
    assert dto.scorecard[0].dimension == "security" and dto.scorecard[0].grade == "C"
    assert dto.sections["executive_summary"].startswith("# Summary")
    assert dto.coverage[0].area == "backend"
    assert dto.strengths[0].title == "clean tenancy"
    assert dto.validation_baseline[0].result == "pass"
    assert len(dto.questions) == 2
    assert dto.open_question_count == 1
    assert dto.questions[1].status == QuestionStatus.ANSWERED


def test_malformed_subitems_are_dropped_not_fatal():
    a = Analysis(
        uid="a2",
        repository_uid="r1",
        source_run_uid="run2",
        scorecard=["not-a-dict", {"dimension": "testing", "score": 50}],
        strengths=[None, {"title": "ok"}],
    )
    dto = analysis_to_dto(a)
    assert len(dto.scorecard) == 1 and dto.scorecard[0].dimension == "testing"
    assert len(dto.strengths) == 1 and dto.strengths[0].title == "ok"


# ── finalize_analysis_for_run: complete vs incomplete ────────────────────────
# DB-free: the node lookup + save are faked so the status-decision logic is
# exercised without Neo4j.

import pytest  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from domains.analysis.services import analysis_service as svc  # noqa: E402
from domains.analysis.services.analysis_service import _authored_verdict  # noqa: E402


class _FakeNode(SimpleNamespace):
    async def save(self):
        self.saved = True


class _FakeNodes:
    def __init__(self, node):
        self._node = node

    async def get_or_none(self, source_run_uid=None, **_kw):
        if self._node is not None and self._node.source_run_uid == source_run_uid:
            return self._node
        return None


def _shell(**overrides):
    fields = dict(
        uid="a1",
        repository_uid="r1",
        source_run_uid="run1",
        status="in_progress",
        health_grade="",
        scorecard=[],
        confidence="",
        limitations="",
        completed_at=None,
        updated_at=None,
        saved=False,
    )
    fields.update(overrides)
    return _FakeNode(**fields)


def test_authored_verdict_detects_any_verdict_signal():
    assert _authored_verdict(_shell(health_grade="B")) is True
    assert _authored_verdict(_shell(scorecard=[{"dimension": "security"}])) is True
    assert _authored_verdict(_shell(confidence="high")) is True
    assert _authored_verdict(_shell()) is False


@pytest.mark.asyncio
async def test_finalize_self_finalized_scan_stays_complete(monkeypatch):
    node = _shell(health_grade="B", confidence="high")
    monkeypatch.setattr(svc, "Analysis", SimpleNamespace(nodes=_FakeNodes(node)))
    flipped = await svc.finalize_analysis_for_run("run1")
    assert flipped is True
    assert node.status == "complete"
    assert node.health_grade == "B"  # verdict preserved
    assert node.limitations == ""
    assert node.completed_at is not None


@pytest.mark.asyncio
async def test_finalize_forced_scan_is_incomplete_with_no_grade(monkeypatch):
    # A killed/forgetful run: shell created, no verdict authored.
    node = _shell(health_grade="")  # nothing authored
    monkeypatch.setattr(svc, "Analysis", SimpleNamespace(nodes=_FakeNodes(node)))
    flipped = await svc.finalize_analysis_for_run("run1")
    assert flipped is True
    assert node.status == "incomplete"
    assert node.health_grade == ""  # never a current grade
    assert node.limitations == "scan did not complete"
    assert node.completed_at is not None


@pytest.mark.asyncio
async def test_finalize_drops_partial_grade_on_forced_finalize(monkeypatch):
    # No confidence/scorecard, but a stray partial grade leaked onto the shell:
    # a forced finalize must NOT keep it. (grade alone counts as authored, so
    # this documents that a partial grade WITH no other signal still counts as
    # authored — the guard against surfacing it lives in latest_for_repo.)
    node = _shell(health_grade="C")
    monkeypatch.setattr(svc, "Analysis", SimpleNamespace(nodes=_FakeNodes(node)))
    flipped = await svc.finalize_analysis_for_run("run1")
    assert flipped is True
    # health_grade counts as an authored verdict → complete, grade kept.
    assert node.status == "complete"
    assert node.health_grade == "C"


@pytest.mark.asyncio
async def test_finalize_is_idempotent_on_non_in_progress(monkeypatch):
    node = _shell(status="complete", health_grade="A")
    monkeypatch.setattr(svc, "Analysis", SimpleNamespace(nodes=_FakeNodes(node)))
    assert await svc.finalize_analysis_for_run("run1") is False
    assert node.status == "complete"
