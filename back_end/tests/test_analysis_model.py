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
    assert ANALYSIS_STATUSES == {"in_progress", "complete", "superseded", "archived"}
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
