"""End-of-run outcome summary — pure decision logic.

The agent reports {summary, did, skipped, succeeded, failed, next_steps}
through complete_run (MCP or trailer); the merge rule decides whether an
incoming call may replace what the Run already stores.
"""

from domains.platform_tools.complete_run import (
    build_outcome,
    canonical_final_status,
    extract_outcome,
    merge_summary,
)

# --- build_outcome / extract_outcome ----------------------------------------


def test_build_outcome_drops_empty_sections_and_strips_items():
    outcome = build_outcome(
        summary="  audited auth flow  ",
        did=["checked middleware", "  ", ""],
        skipped=[],
        failed=None,
        next_steps="add rate-limit test",  # bare string tolerated
    )
    assert outcome == {
        "text": "audited auth flow",
        "did": ["checked middleware"],
        "next_steps": ["add rate-limit test"],
    }


def test_build_outcome_coerces_non_string_items():
    assert build_outcome(did=[1, {"x": "y"}])["did"] == ["1", "{'x': 'y'}"]


def test_build_outcome_ignores_non_list_garbage():
    assert build_outcome(summary="", did={"not": "a list"}) == {}


def test_extract_outcome_reads_trailer_complete_run_args():
    outcome = extract_outcome(
        {
            "summary": "done",
            "failed": ["mypy step errored"],
            "final_status": "ended",  # non-summary args are ignored
        }
    )
    assert outcome == {"text": "done", "failed": ["mypy step errored"]}


# --- merge_summary ------------------------------------------------------------


def test_structured_outcome_replaces_anything():
    existing = {"text": "old", "did": ["old work"]}
    incoming = {"text": "new", "did": ["new work"], "next_steps": ["ship it"]}
    assert merge_summary(existing, incoming) == incoming


def test_text_only_fallback_fills_empty_summary():
    incoming = {"text": "claude_code finished in 12.3s (exit=0)"}
    assert merge_summary({}, incoming) == incoming


def test_text_only_never_clobbers_structured_summary():
    # The claude agent already reported over MCP mid-run; the lifecycle's
    # synthetic finalize text must not overwrite it.
    existing = {"text": "audited auth", "did": ["checked middleware"]}
    incoming = {"text": "claude_code finished in 12.3s (exit=0)"}
    assert merge_summary(existing, incoming) == existing


def test_text_only_may_replace_prior_text_only():
    assert merge_summary({"text": "first turn"}, {"text": "second turn"}) == {
        "text": "second turn"
    }


def test_empty_incoming_keeps_existing():
    existing = {"text": "kept"}
    assert merge_summary(existing, {}) == existing


# --- canonical_final_status ---------------------------------------------------


def test_completed_is_normalized_to_awaiting_input():
    # There is no terminal "completed" run state; an agent that self-reports it
    # means a finished turn, which is awaiting_input. Without this the write-run
    # push + draft PR never fire and the run accepts no follow-up.
    assert canonical_final_status("completed") == "awaiting_input"


def test_other_statuses_pass_through_unchanged():
    for status in ("awaiting_input", "ended", "failed", "limit_exceeded"):
        assert canonical_final_status(status) == status
