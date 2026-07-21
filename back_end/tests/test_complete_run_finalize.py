"""complete_run finalize — status aliasing keeps the run followable, but the
agent's ORIGINAL self-report must survive (usage + audit payload) so the UI
and the notification feed can tell "done" apart from "genuinely waiting on a
human". DB-free: the Run lookup and audit writer are faked."""

from importlib import import_module
from types import SimpleNamespace

import pytest

# The package __init__ rebinds `complete_run` to the function — import the
# module itself for monkeypatching.
cr = import_module("domains.platform_tools.complete_run")

pytestmark = pytest.mark.asyncio


class _FakeRun(SimpleNamespace):
    async def save(self):
        return self


def _run(**overrides):
    base = dict(
        uid="run-1",
        title="review PR #7",
        status="running",
        executor="claude_code",
        usage={},
        output_refs=[],
        summary={},
        started_at=None,
        completed_at=None,
        updated_at=None,
        duration_ms=0,
        raw_artifact_uri="",
        parse_status="",
        error="",
    )
    base.update(overrides)
    return _FakeRun(**base)


@pytest.fixture
def finalize(monkeypatch):
    """Wire complete_run onto a fake run + audit capture; returns (run, audits)."""
    run = _run()
    audits: list[dict] = []

    class _Nodes:
        async def get_or_none(self, *, uid):
            return run if uid == run.uid else None

    monkeypatch.setattr(cr, "Run", SimpleNamespace(nodes=_Nodes()))

    async def _capture_audit(**kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(cr, "write_audit", _capture_audit)
    return run, audits


async def test_self_reported_completed_survives_the_alias(finalize):
    run, audits = finalize
    result = await cr.complete_run(run_uid="run-1", summary="all good", final_status="completed")

    # Canonical status still awaiting_input — the follow-up loop and the
    # write-gate hooks depend on it.
    assert result["status"] == "awaiting_input"
    assert run.status == "awaiting_input"
    # But the agent said "completed", and that must survive.
    assert run.usage["self_reported_status"] == "completed"

    (audit,) = audits
    assert audit["kind"] == "run.awaiting_input"
    assert audit["payload"]["self_reported_status"] == "completed"


async def test_explicit_awaiting_input_is_recorded_as_such(finalize):
    run, audits = finalize
    await cr.complete_run(run_uid="run-1", summary="need a decision", final_status="awaiting_input")
    assert run.usage["self_reported_status"] == "awaiting_input"
    assert audits[0]["payload"]["self_reported_status"] == "awaiting_input"


async def test_audit_payload_carries_the_run_title(finalize):
    # The notification feed renders payload["title"] — without it every run
    # notification is a bare label.
    run, audits = finalize
    await cr.complete_run(run_uid="run-1", summary="done", final_status="completed")
    assert audits[0]["payload"]["title"] == "review PR #7"


async def test_refinalize_does_not_duplicate_the_audit(finalize):
    # An MCP self-completing agent calls complete_run mid-run; the lifecycle
    # finalize calls it AGAIN with the adapter result. One completion, one
    # audit event — the notification fires on the status transition only.
    run, audits = finalize
    await cr.complete_run(run_uid="run-1", summary="agent report", final_status="completed")
    await cr.complete_run(run_uid="run-1", summary="lifecycle finalize", final_status="awaiting_input")
    assert len(audits) == 1


# ── Coverage contract (covered/skipped paths + per-lens verdicts) ────────────


async def test_build_coverage_normalizes_and_drops_empties():
    coverage = cr.build_coverage(
        covered_paths=["  src/a.py ", "", "src/b.py"],
        skipped_paths="docs/",  # bare string coerces like build_outcome's lists
        lens_verdicts=[
            {"lens": "bugs", "verdict": "checked-clean", "note": "  all good "},
            {"lens": "security", "verdict": "checked-findings"},
        ],
    )
    assert coverage == {
        "covered_paths": ["src/a.py", "src/b.py"],
        "skipped_paths": ["docs/"],
        "lens_verdicts": [
            {"lens": "bugs", "verdict": "checked-clean", "note": "all good"},
            {"lens": "security", "verdict": "checked-findings"},
        ],
    }
    assert cr.build_coverage() == {}
    assert cr.build_coverage(covered_paths=[], lens_verdicts="not-a-list") == {}


async def test_build_coverage_drops_invalid_verdict_entries_without_raising():
    coverage = cr.build_coverage(
        lens_verdicts=[
            {"lens": "bugs", "verdict": "looks-fine"},  # unknown verdict
            {"lens": "", "verdict": "checked-clean"},  # no lens name
            "not-a-dict",
            {"lens": "tests", "verdict": "skipped"},  # the one valid entry
        ]
    )
    assert coverage == {"lens_verdicts": [{"lens": "tests", "verdict": "skipped"}]}


async def test_complete_run_stores_coverage_in_usage_and_summary(finalize):
    run, _ = finalize
    verdicts = [{"lens": "bugs", "verdict": "checked-clean"}]
    await cr.complete_run(
        run_uid="run-1",
        summary="done",
        covered_paths=["src/a.py"],
        skipped_paths=["src/legacy/"],
        lens_verdicts=verdicts,
        final_status="completed",
    )
    assert run.usage["coverage"] == {
        "covered_paths": ["src/a.py"],
        "skipped_paths": ["src/legacy/"],
        "lens_verdicts": verdicts,
    }
    # The verdicts also land in the human-facing summary.
    assert run.summary["lens_verdicts"] == verdicts


async def test_lifecycle_refinalize_does_not_erase_agent_coverage(finalize):
    # MCP self-completion reports coverage; the lifecycle's second, coverage-
    # less complete_run call must not wipe usage["coverage"].
    run, _ = finalize
    await cr.complete_run(
        run_uid="run-1",
        covered_paths=["src/a.py"],
        lens_verdicts=[{"lens": "bugs", "verdict": "checked-findings"}],
        final_status="completed",
    )
    await cr.complete_run(run_uid="run-1", summary="lifecycle finalize", final_status="awaiting_input")
    assert run.usage["coverage"]["covered_paths"] == ["src/a.py"]
    assert run.usage["coverage"]["lens_verdicts"] == [
        {"lens": "bugs", "verdict": "checked-findings"}
    ]


async def test_extract_coverage_reads_trailer_complete_run_args():
    coverage = cr.extract_coverage(
        {
            "summary": "irrelevant here",
            "covered_paths": ["a.py"],
            "lens_verdicts": [{"lens": "bugs", "verdict": "skipped", "note": "ran out"}],
        }
    )
    assert coverage["covered_paths"] == ["a.py"]
    assert coverage["lens_verdicts"] == [
        {"lens": "bugs", "verdict": "skipped", "note": "ran out"}
    ]


async def test_envelope_harvest_carries_coverage_to_the_finalizer():
    # CLI executors: the trailer complete_run entry is harvested, not
    # dispatched — its coverage must ride the outcome dict into the lifecycle
    # finalize (which passes covered_paths/skipped_paths/lens_verdicts back to
    # complete_run). Without this, envelope-path lens_verdicts vanish.
    from domains.executors._shared import execute_envelope_tool_calls

    verdicts = [{"lens": "security", "verdict": "checked-clean"}]
    results, refs, outcome = await execute_envelope_tool_calls(
        calls=[
            {
                "tool": "complete_run",
                "args": {
                    "summary": "swept the area",
                    "did": ["checked auth"],
                    "covered_paths": ["src/auth.py"],
                    "skipped_paths": ["src/vendored/"],
                    "lens_verdicts": verdicts,
                },
            }
        ],
        req=SimpleNamespace(run_uid="run-1", repository_uid="repo-1"),
        executor_value="codex",
    )
    assert results == [] and refs == []
    assert outcome["did"] == ["checked auth"]
    assert outcome["covered_paths"] == ["src/auth.py"]
    assert outcome["skipped_paths"] == ["src/vendored/"]
    assert outcome["lens_verdicts"] == verdicts
