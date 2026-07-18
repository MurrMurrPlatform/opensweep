"""Thread intent builders (style mirror: tests/test_implement_run_intent.py)."""

from types import SimpleNamespace

from domains.threads.services.intents import (
    build_implement_addendum,
    build_thread_session_intent,
)


def _ticket():
    return SimpleNamespace(
        uid="t-1",
        title="Fix token refresh",
        description="Refresh tokens expire early",
        acceptance_criteria=["tokens refresh silently"],
        priority="high",
    )


def test_session_intent_is_interactive_and_stage_gated():
    intent = build_thread_session_intent(_ticket(), "th-1")
    # Batched interrogation: independent questions all in one turn.
    assert "in ONE turn" in intent
    assert "delivers all answers together" in intent
    assert "do not edit files and do not commit" in intent
    assert "t-1" in intent and "th-1" in intent


def test_session_intent_names_the_plan_tool():
    intent = build_thread_session_intent(_ticket(), "th-1")
    assert "opensweep_platform_submit_thread_plan" in intent
    assert "opensweep_platform_update_ticket" in intent


def test_session_intent_stages_the_lifecycle():
    intent = build_thread_session_intent(_ticket(), "th-1")
    # Rev2: one conversation for the whole lifecycle, staged by the platform.
    assert "CURRENT STAGE: PLANNING" in intent
    assert "'GO —'" in intent or "GO message" in intent
    assert "do not edit files and do not commit" in intent
    # The stage rules must explicitly survive follow-up turns (the observed
    # failure mode: agent starts implementing right after an answer).
    assert "after the user answers a question" in intent


def test_addendum_contains_plan_and_decisions():
    out = build_implement_addendum("## Plan\n1. do X", "## Decisions\n- (user) soft gate")
    assert "## Plan" in out and "soft gate" in out
    assert out.index("Plan") < out.index("Decisions")


def test_addendum_empty_when_nothing_to_carry():
    assert build_implement_addendum("", "") == ""


def test_addendum_plan_only():
    out = build_implement_addendum("## Plan\n1. do X", "")
    assert "## Plan" in out and "Decisions" not in out


def test_session_intent_nudges_native_todos():
    intent = build_thread_session_intent(_ticket(), "th-1")
    assert "TodoWrite" in intent and "mirrors it" in intent
