"""P1 — analysis/health integrity, against the real test Neo4j (localhost:7999).

Covers the finding roll-up + repo isolation, `latest_for_repo` selection
(superseded/incomplete exclusion, newest-first), `finalize_analysis_for_run`
(forced-incomplete vs self-finalized vs idempotent), and the
`get_or_create_analysis` uniqueness race (which relies on the real
source_run_uid unique constraint being active).
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from domains.analysis.models import Analysis
from domains.analysis.schemas import AnalysisStatus
from domains.analysis.services.analysis_service import (
    AnalysisService,
    finalize_analysis_for_run,
    get_or_create_analysis,
)
from domains.findings.models import Finding

pytestmark = pytest.mark.integration


def _repo() -> str:
    return "repo-" + uuid4().hex[:8]


def _run() -> str:
    return "run-" + uuid4().hex[:8]


async def _make_finding(repo: str, run_uid: str, severity: str, *, status: str = "open") -> Finding:
    f = Finding(
        uid=uuid4().hex,
        repository_uid=repo,
        kind="defect",
        severity=severity,
        title="f",
        dedupe_key=uuid4().hex,
        source_run_uid=run_uid,
        status=status,
    )
    await f.save()
    return f


async def _make_analysis(
    repo: str,
    run_uid: str,
    *,
    status: str = "complete",
    health_grade: str = "B",
    created_at: datetime | None = None,
) -> Analysis:
    a = Analysis(
        uid=uuid4().hex,
        repository_uid=repo,
        source_run_uid=run_uid,
        status=status,
        health_grade=health_grade,
    )
    await a.save()
    if created_at is not None:
        a.created_at = created_at
        await a.save()
    return a


# ── _attach_finding_rollup + latest_for_repo ────────────────────────────────


async def test_finding_rollup_by_severity_with_repo_isolation():
    repo = _repo()
    other_repo = _repo()
    run_uid = _run()
    other_run = _run()

    await _make_finding(repo, run_uid, "high")
    await _make_finding(repo, run_uid, "high")
    await _make_finding(repo, run_uid, "low")
    # Same repo, DIFFERENT run — joined by source_run_uid, so excluded.
    await _make_finding(repo, other_run, "critical")
    # Different repo entirely — excluded.
    await _make_finding(other_repo, other_run, "critical")

    await _make_analysis(repo, run_uid)
    svc = AnalysisService()
    dto = await svc.latest_for_repo(repo)

    assert dto is not None
    assert dto.finding_count == 3
    assert dto.findings_by_severity == {"high": 2, "low": 1}


async def test_latest_for_repo_excludes_superseded_and_incomplete_newest_first():
    repo = _repo()
    now = datetime.now(UTC)

    # Oldest complete (should lose to the newer complete).
    await _make_analysis(
        repo, _run(), status="complete", health_grade="C", created_at=now - timedelta(days=3)
    )
    # Superseded — excluded even though newer.
    await _make_analysis(
        repo, _run(), status="superseded", health_grade="A", created_at=now - timedelta(days=2)
    )
    # Incomplete — excluded (no current grade) even though newest.
    await _make_analysis(
        repo, _run(), status="incomplete", health_grade="", created_at=now - timedelta(hours=1)
    )
    # The winner: newest COMPLETE.
    winner = await _make_analysis(
        repo, _run(), status="complete", health_grade="B", created_at=now - timedelta(days=1)
    )

    dto = await AnalysisService().latest_for_repo(repo)
    assert dto is not None
    assert dto.uid == winner.uid
    assert dto.health_grade == "B"


async def test_latest_for_repo_all_incomplete_returns_none():
    repo = _repo()
    await _make_analysis(repo, _run(), status="incomplete", health_grade="")
    assert await AnalysisService().latest_for_repo(repo) is None


# ── finalize_analysis_for_run ───────────────────────────────────────────────


async def test_finalize_forced_shell_becomes_incomplete():
    repo = _repo()
    run_uid = _run()
    # A shell — in_progress, no verdict (no health_grade/scorecard/confidence).
    a = Analysis(
        uid=uuid4().hex,
        repository_uid=repo,
        source_run_uid=run_uid,
        status="in_progress",
    )
    await a.save()

    flipped = await finalize_analysis_for_run(run_uid)
    assert flipped is True

    a = await Analysis.nodes.get(source_run_uid=run_uid)
    assert a.status == "incomplete"
    assert (a.health_grade or "") == ""  # partial grade dropped
    assert a.limitations == "scan did not complete"
    assert a.completed_at is not None


async def test_finalize_self_finalized_stays_complete():
    repo = _repo()
    run_uid = _run()
    a = Analysis(
        uid=uuid4().hex,
        repository_uid=repo,
        source_run_uid=run_uid,
        status="in_progress",
        health_grade="A",  # agent authored a verdict
    )
    await a.save()

    flipped = await finalize_analysis_for_run(run_uid)
    assert flipped is True

    a = await Analysis.nodes.get(source_run_uid=run_uid)
    assert a.status == "complete"
    assert a.health_grade == "A"  # preserved


async def test_finalize_is_idempotent():
    repo = _repo()
    run_uid = _run()
    a = Analysis(
        uid=uuid4().hex,
        repository_uid=repo,
        source_run_uid=run_uid,
        status="in_progress",
    )
    await a.save()

    assert await finalize_analysis_for_run(run_uid) is True
    # Second call: already terminal (incomplete), no flip.
    assert await finalize_analysis_for_run(run_uid) is False

    a = await Analysis.nodes.get(source_run_uid=run_uid)
    assert a.status == "incomplete"


async def test_finalize_unknown_run_returns_false():
    assert await finalize_analysis_for_run(_run()) is False


# ── get_or_create_analysis uniqueness ───────────────────────────────────────


async def test_get_or_create_analysis_returns_same_node():
    repo = _repo()
    run_uid = _run()

    first = await get_or_create_analysis(repository_uid=repo, source_run_uid=run_uid)
    second = await get_or_create_analysis(repository_uid=repo, source_run_uid=run_uid)

    assert first.uid == second.uid

    # Exactly one Analysis exists for the run — the unique constraint held.
    rows = list(await Analysis.nodes.filter(source_run_uid=run_uid))
    assert len(rows) == 1


async def test_get_or_create_analysis_constraint_blocks_duplicate():
    """A raw second insert with the same source_run_uid must be rejected by the
    unique constraint (proves create_constraints ran on the test DB)."""
    repo = _repo()
    run_uid = _run()
    await get_or_create_analysis(repository_uid=repo, source_run_uid=run_uid)

    dup = Analysis(
        uid=uuid4().hex,
        repository_uid=repo,
        source_run_uid=run_uid,
        status="in_progress",
    )
    with pytest.raises(Exception):
        await dup.save()
