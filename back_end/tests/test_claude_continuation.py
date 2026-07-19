from domains.executors.claude_code import (
    _CONTINUATION_NUDGE,
    build_continuation_argv,
    soft_wall,
)

ARGV = ["claude", "-p", "the instruction", "--append-system-prompt", "sys", "--output-format", "stream-json"]


def test_continuation_swaps_instruction_and_appends_resume():
    out = build_continuation_argv(
        ARGV, instruction="the instruction", nudge=_CONTINUATION_NUDGE, session_id="sid-1"
    )
    assert out is not None
    assert out[out.index("-p") + 1] == _CONTINUATION_NUDGE
    assert out[-2:] == ["--resume", "sid-1"]
    assert "the instruction" not in out


def test_no_session_id_means_no_continuation():
    assert build_continuation_argv(ARGV, instruction="the instruction", nudge="n", session_id="") is None


def test_unfindable_instruction_means_no_continuation():
    assert build_continuation_argv(ARGV, instruction="not present", nudge="n", session_id="sid") is None


def test_soft_wall_reserves_winddown_share():
    assert soft_wall(3600) == 3240  # 90%
    assert soft_wall(None) is None
    assert soft_wall(60) == 54
