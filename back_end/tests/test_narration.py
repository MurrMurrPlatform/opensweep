"""Narration sidecar: template lines + stream integration (Phase 2).

Contract per the unified-dev-flow spec: given transcript events, narration
events are well-formed (`text`, `covers_seq`), only tool calls narrate, and
narration is executor-agnostic (input is the normalized event, not executor
output).
"""

from domains.investigations.services.narration import (
    narrate_tool_use,
    narration_for_event,
)


def test_read_edit_bash_templates():
    assert narrate_tool_use("Read", {"file_path": "auth/service.py"}) == "Reading auth/service.py"
    assert narrate_tool_use("Edit", {"file_path": "a.py"}) == "Editing a.py"
    assert narrate_tool_use("Write", {"file_path": "b.py"}) == "Writing b.py"
    assert narrate_tool_use("Bash", {"command": "pytest -q"}) == "Running `pytest -q`"


def test_platform_tools_get_friendly_lines():
    assert narrate_tool_use("opensweep_platform_update_ticket", {}) == "Updating the ticket"
    assert (
        narrate_tool_use("mcp__opensweep__submit_thread_plan", {})
        == "Writing the implementation plan"
    )


def test_unknown_tool_still_narrates_generically():
    assert narrate_tool_use("SomeCustomTool", {}) == "Using the SomeCustomTool tool"


def test_long_values_are_truncated():
    line = narrate_tool_use("Bash", {"command": "x" * 500})
    assert len(line) < 140


def test_narration_only_for_tool_use():
    assert narration_for_event({"type": "assistant_text", "text": "hi", "seq": 3}) is None
    assert narration_for_event({"type": "narration", "text": "hi", "seq": 4}) is None
    out = narration_for_event({"type": "tool_use", "name": "Read", "input": {"file_path": "x"}, "seq": 7})
    assert out == {"text": "Reading x", "covers_seq": 7}


def test_append_event_emits_narration_line(tmp_path, monkeypatch):
    import domains.investigations.services.run_events as re_mod

    monkeypatch.setattr(re_mod.settings, "ARTIFACT_STORE_ROOT", str(tmp_path), raising=False)
    re_mod.append_event("run-x", "tool_use", turn=1, name="Read", input={"file_path": "a.py"})
    events = re_mod.read_events("run-x")
    types = [e["type"] for e in events]
    assert types == ["tool_use", "narration"]
    narration = events[1]
    assert narration["text"] == "Reading a.py"
    assert narration["covers_seq"] == events[0]["seq"]
    assert narration["seq"] > events[0]["seq"]
