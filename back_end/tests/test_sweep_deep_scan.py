"""Deep-scan surface: whole-repo plan → sweep → synthesize.

run_deep_scan itself touches Neo4j + dispatch; these cover the DB-free
contract — signature, result shape, playbook mapping, and the intent
composition (the seeded "deep-scan" agent base is the instructions layer;
the Analysis authoring contract + scope ride in the structural slot, so a
focus/budget/overlay must AUGMENT the instructions, never displace the
contract). Composition degrades layer by layer without a DB: the platform
base resolves to the in-code fallback, the org overlay to none.
"""

import inspect

from domains.investigations.services.playbooks import playbook_for_job_type
from domains.investigations.services.sweep import (
    DeepScanResult,
    _deep_scan_intent,
    run_deep_scan,
)


def test_run_deep_scan_signature():
    params = inspect.signature(run_deep_scan).parameters
    assert {
        "repository_uid",
        "triggered_by",
        "agent_prompt_uid",
        "custom_intent",
        "max_findings",
        "run_policy_uid",
    } <= set(params)


def test_deep_scan_result_defaults():
    result = DeepScanResult(repository_uid="r1")
    assert result.run_uid == ""
    assert result.errors == []


def test_deep_scan_job_type_maps_to_ask_playbook():
    # "ask" is the playbook that gets analyzer candidates (§E) and a Checked
    # stamp — both wanted for a deep scan. The "deep-scan" key exists only in
    # AGENT_PLAYBOOKS (instruction base + org overlay), not as a run playbook.
    assert playbook_for_job_type("deep-scan") == "ask"


async def test_intent_carries_the_phases():
    intent = await _deep_scan_intent()
    assert "Survey & plan" in intent
    assert "Sweep area by area" in intent
    assert "Baseline" in intent
    # Whole-repo scope is always present.
    assert "whole repository" in intent.lower()


async def test_intent_directs_analysis_authoring_tools():
    # The deep-scan prompt must tell the agent to build the Analysis via the
    # authoring tools — that's what makes the run produce a first-class report.
    intent = await _deep_scan_intent()
    for tool in ("upsert_analysis", "set_analysis_section", "add_analysis_note", "ask_question"):
        assert tool in intent, f"deep-scan prompt should mention {tool}"
    # Staged implementation plan + top changes sections are called out.
    assert "implementation_plan" in intent and "top_changes" in intent


async def test_focus_and_budget_augment_rather_than_replace_instructions():
    intent = await _deep_scan_intent(
        focus="weight toward security and the multi-tenancy boundaries",
        budget_line="File at most 25 findings across the whole scan.",
    )
    # Regression guard: the instructions must survive alongside the
    # focus/budget — they ride in the structural slot, never custom_intent.
    assert "Sweep area by area" in intent
    assert "weight toward security" in intent
    assert "at most 25 findings" in intent


async def test_explicit_prompt_override_keeps_the_structural_contract():
    # An explicit prompt body replaces the instructions layer (power-user
    # override), but scope + focus + the Analysis authoring contract still
    # ride along in the structural slot.
    intent = await _deep_scan_intent(
        prompt_body="Only look at the payment code.",
        focus="ignore tests",
    )
    assert "Only look at the payment code." in intent
    assert "whole repository" in intent.lower()
    assert "ignore tests" in intent
    assert "upsert_analysis" in intent  # contract survives the override
