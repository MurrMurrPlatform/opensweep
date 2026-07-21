"""prompt_kit.stance_block — the budget+stance paragraph rendered into every
executor instruction (successor of _shared.budget_briefing + the review
depth_block)."""

from domains.executors.prompt_kit import stance_block


class _P:
    max_tool_turns = 200
    max_continuation_passes = 3
    max_files_touched = 100
    warn_at_pct = 80


class _Unlimited:
    max_tool_turns = None
    max_continuation_passes = None
    max_files_touched = None
    warn_at_pct = 80


def test_bounded_policy_renders_numbers_and_winddown_rule():
    text = stance_block(_P(), 3600, "normal")
    assert "60 minutes" in text
    assert "200 tool turns" in text
    assert "3 continuation passes" in text
    assert "80%" in text
    assert "complete_run" in text


def test_unlimited_policy_renders_unbounded_briefing():
    text = stance_block(_Unlimited(), None, "unlimited")
    assert "no fixed budget" in text
    assert "complete_run" in text


def test_no_policy_no_wall_is_still_nonempty():
    assert "complete_run" in stance_block(None, None, "normal")


def test_no_dollar_language():
    for tier in ("short", "normal", "deep", "unlimited"):
        text = stance_block(_P(), 3600, tier)
        assert "$" not in text
        assert "dollar" not in text.lower()


def test_files_touched_ceiling_renders_only_for_write_runs():
    read = stance_block(_P(), 3600, "normal")
    write = stance_block(_P(), 3600, "normal", write_run=True)
    assert "files touched" not in read
    assert "~100 files touched" in write


# ── Effort-tier stances ──────────────────────────────────────────────────


def test_short_tier_caps_findings_and_allows_empty_result():
    text = stance_block(_P(), 900, "short")
    assert "at most 5 findings" in text.lower()
    assert "empty result is a valid outcome" in text.lower()


def test_normal_tier_has_no_cap_and_skips_style():
    text = stance_block(_P(), 3600, "normal")
    assert "no hard finding cap" in text.lower()
    assert "style-only" in text.lower()
    assert "subagent" not in text.lower()


def test_deep_tier_works_lens_by_lens_with_subagents():
    text = stance_block(_P(), 14400, "deep")
    assert "lens by lens" in text.lower()
    assert "subagent" in text.lower()
    assert "did not check" in text.lower()


def test_unlimited_tier_runs_to_genuine_completion():
    text = stance_block(_P(), 3600, "unlimited")
    assert "genuine completion" in text.lower()


def test_max_findings_knob_caps_every_tier():
    assert "at most 12 findings" in stance_block(_P(), None, "short", 12).lower()
    assert "at most 3 findings" in stance_block(_P(), None, "normal", 3).lower()
    assert "at most 8 findings" in stance_block(_P(), None, "deep", 8).lower()


def test_legacy_quick_alias_matches_short():
    assert stance_block(_P(), 900, "quick") == stance_block(_P(), 900, "short")
