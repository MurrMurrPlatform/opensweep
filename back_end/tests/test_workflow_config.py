"""Pure-Python tests for the per-repo workflow config.

DB-bound flows (set_workflow validation, trigger integration) are
integration-tested; here we pin the normalization, defaults, and the
guidance-section composition every trigger relies on.
"""

from domains.delivery.services.fix_run_service import build_fix_intent
from domains.delivery.services.review_run_service import build_review_intent
from domains.repositories.services.workflow import (
    AUTO_STAGES,
    DEPTHS,
    STAGES,
    _normalize,
    guidance_section,
    stage_for_run,
)

# Inherit-everything defaults for the per-stage run overrides.
_NO_OVERRIDES = {"provider_uid": "", "model": "", "max_wall_seconds": 0, "run_policy_uid": ""}


class _PR:
    github_number = 7
    title = "t"
    head_ref = "feature/x"
    base_ref = "main"
    head_sha = "a" * 40
    repository_uid = "r1"
    uid = "pr1"


def test_stages_cover_the_pipeline():
    assert STAGES == ("ask", "analysis", "discover", "review", "fix", "implement", "verify", "document")
    assert AUTO_STAGES == ("review", "fix", "verify")
    assert set(AUTO_STAGES) <= set(STAGES)
    assert DEPTHS == ("quick", "normal", "deep")


def test_normalize_fills_all_stages_with_defaults():
    config = _normalize(None)
    assert set(config) == set(STAGES)
    # Auto reviews fire on every push — the stage default is precision (quick).
    assert config["review"] == {"agent_uid": "", "auto": True, "depth": "quick", **_NO_OVERRIDES}
    assert config["fix"] == {"agent_uid": "", "auto": False, "depth": "normal", **_NO_OVERRIDES}
    assert config["ask"] == {"agent_uid": "", "auto": False, "depth": "normal", **_NO_OVERRIDES}
    assert config["verify"] == {"agent_uid": "", "auto": False, "depth": "normal", **_NO_OVERRIDES}


def test_normalize_preserves_explicit_values_and_drops_junk():
    config = _normalize(
        {
            "review": {"agent_uid": "p1", "auto": False, "junk": 1, "depth": "deep"},
            "document": {"agent_uid": "p2"},
            "ask": {"depth": "bogus"},
        }
    )
    assert config["review"] == {"agent_uid": "p1", "auto": False, "depth": "deep", **_NO_OVERRIDES}
    assert config["document"] == {"agent_uid": "p2", "auto": False, "depth": "normal", **_NO_OVERRIDES}
    # Junk depth falls back to the stage default, never leaks through.
    assert config["ask"]["depth"] == "normal"
    assert "junk" not in config["review"]


def test_normalize_run_overrides():
    config = _normalize(
        {
            "discover": {"provider_uid": "prov1", "model": " claude-opus-4-8 ", "max_wall_seconds": 1800},
            "review": {"max_wall_seconds": "900"},
            "ask": {"max_wall_seconds": "junk", "model": None},
            "analysis": {"run_policy_uid": "pol-deep"},
        }
    )
    assert config["discover"]["provider_uid"] == "prov1"
    assert config["discover"]["model"] == "claude-opus-4-8"
    assert config["discover"]["max_wall_seconds"] == 1800
    # Numeric strings coerce; junk and negatives collapse to 0 (inherit).
    assert config["review"]["max_wall_seconds"] == 900
    assert config["ask"]["max_wall_seconds"] == 0
    assert config["ask"]["model"] == ""
    # A stage can pin a full run policy; empty everywhere else = inherit.
    assert config["analysis"]["run_policy_uid"] == "pol-deep"
    assert config["discover"]["run_policy_uid"] == ""


def test_stage_for_run_maps_job_types_and_playbooks():
    # Saved Investigations: job_type is the sharper signal.
    assert stage_for_run("generate-docs", "ask") == "discover"
    assert stage_for_run("deep-scan", "ask") == "analysis"
    assert stage_for_run("audit", "ask") == "ask"
    assert stage_for_run("sweep", "ask") == "ask"
    assert stage_for_run("audit-stale", "ask") == "ask"
    assert stage_for_run("document", "document") == "document"
    assert stage_for_run("implement", "implement") == "implement"
    # Direct runs: fall back to the playbook.
    assert stage_for_run("", "review") == "review"
    assert stage_for_run("", "fix") == "fix"
    assert stage_for_run("", "verify") == "verify"
    assert stage_for_run("", "ask") == "ask"
    # Chat runs are governed by no stage.
    assert stage_for_run("", "chat") == ""
    assert stage_for_run("", "") == ""


def test_guidance_section_empty_when_no_prompt():
    assert guidance_section("review", None) == ""
    assert guidance_section("review", "   ") == ""


def test_guidance_section_frames_body_as_advisory():
    section = guidance_section("review", "Check for N+1 queries.")
    assert "Review guidance" in section
    assert "Check for N+1 queries." in section
    assert "never overrides the structural" in section


def test_review_intent_appends_guidance_after_contract():
    base = build_review_intent(_PR(), {"default": "high"})
    with_guidance = build_review_intent(
        _PR(), {"default": "high"}, guidance="Watch for missing pagination."
    )
    assert base in with_guidance  # structural contract intact, guidance appended
    assert "Watch for missing pagination." in with_guidance
    assert with_guidance.index("submit_verdict") < with_guidance.index("pagination")


def test_fix_intent_appends_guidance_after_contract():
    findings = [{"resolution_uid": "res1", "title": "bug"}]
    base = build_fix_intent(_PR(), findings, [])
    with_guidance = build_fix_intent(_PR(), findings, [], guidance="Prefer stdlib fixes.")
    assert base in with_guidance
    assert "Prefer stdlib fixes." in with_guidance
