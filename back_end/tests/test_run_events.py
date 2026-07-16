"""Structured run transcript — event store roundtrip, stream translation,
argv flags (PLATFORM_V3_DESIGN.md §4)."""

import json

from config import settings
from domains.executors.claude_code import ensure_stream_json_flags
from domains.executors.stream_events import ClaudeStreamTranslator, stream_event_delta
from domains.investigations.services import run_events
from domains.investigations.services.run_events import (
    append_event,
    events_path,
    read_events,
    read_events_from,
)


def _reset_seq(monkeypatch):
    monkeypatch.setattr(run_events, "_next_seq", {})
    monkeypatch.setattr(run_events, "_expected_size", {})


# ── append/read/seq roundtrip ────────────────────────────────────────────────


def test_append_read_after_seq_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(tmp_path))
    _reset_seq(monkeypatch)
    append_event("run1", "assistant_text", text="hello ")
    events = read_events("run1", 0)
    assert [e["type"] for e in events] == ["assistant_text"]
    assert events[0]["seq"] == 1
    assert events[0]["turn"] == 1
    append_event("run1", "tool_use", name="Bash", input="pytest -q")
    tail = read_events("run1", after_seq=events[-1]["seq"])
    assert [e["type"] for e in tail] == ["tool_use"]
    assert tail[0]["seq"] == 2
    # Re-reading past the end yields nothing new.
    assert read_events("run1", after_seq=2) == []


def test_seq_reseeds_from_file_after_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(tmp_path))
    _reset_seq(monkeypatch)
    append_event("run1", "assistant_text", text="a")
    append_event("run1", "assistant_text", text="b")
    _reset_seq(monkeypatch)  # simulate process restart
    append_event("run1", "assistant_text", text="c")
    assert [e["seq"] for e in read_events("run1", 0)] == [1, 2, 3]


def test_seq_reseeds_when_file_grows_under_another_process(tmp_path, monkeypatch):
    # Dispatch ownership can move backend ↔ worker mid-run (quota redispatch,
    # follow-up turns). The other process appends directly to the file; our
    # cached counter is stale and must reseed instead of minting duplicates.
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(tmp_path))
    _reset_seq(monkeypatch)
    append_event("run1", "assistant_text", text="ours")
    with open(events_path("run1"), "a", encoding="utf-8") as fh:  # "other process"
        fh.write(json.dumps({"seq": 5, "ts": "t", "turn": 1, "type": "system"}) + "\n")
    append_event("run1", "assistant_text", text="ours again")
    assert [e["seq"] for e in read_events("run1", 0)] == [1, 5, 6]


def test_read_missing_transcript_is_empty_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(tmp_path))
    assert read_events("never-ran", 0) == []
    assert read_events("never-ran", 42) == []


# ── offset-based live tail (read_events_from) ────────────────────────────────


def test_read_events_from_tracks_byte_offset(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(tmp_path))
    _reset_seq(monkeypatch)
    append_event("run1", "assistant_text", text="a")
    events, offset = read_events_from("run1", 0)
    assert [e["seq"] for e in events] == [1]
    # Nothing new: same offset back, no events.
    assert read_events_from("run1", offset) == ([], offset)
    append_event("run1", "tool_use", name="Bash", input="ls")
    events, offset2 = read_events_from("run1", offset)
    assert [e["seq"] for e in events] == [2]
    assert offset2 > offset


def test_read_events_from_filters_replay_with_after_seq(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(tmp_path))
    _reset_seq(monkeypatch)
    append_event("run1", "assistant_text", text="a")
    append_event("run1", "assistant_text", text="b")
    append_event("run1", "assistant_text", text="c")
    events, offset = read_events_from("run1", 0, after_seq=2)
    assert [e["seq"] for e in events] == [3]
    assert read_events_from("run1", offset) == ([], offset)


def test_read_events_from_leaves_partial_trailing_line(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(tmp_path))
    _reset_seq(monkeypatch)
    append_event("run1", "assistant_text", text="whole")
    with open(events_path("run1"), "a", encoding="utf-8") as fh:
        fh.write('{"seq": 2, "type": "assistant_')  # append in flight
    events, offset = read_events_from("run1", 0)
    assert [e["seq"] for e in events] == [1]
    with open(events_path("run1"), "a", encoding="utf-8") as fh:
        fh.write('text", "turn": 1, "ts": "t", "text": "rest"}\n')
    events, _ = read_events_from("run1", offset)
    assert [e["seq"] for e in events] == [2]


def test_read_events_from_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(tmp_path))
    assert read_events_from("never-ran", 0) == ([], 0)


def test_events_path_is_sanitized_and_under_runs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(tmp_path))
    p = events_path("../../etc/passwd")
    # Slashes are neutralized: the file cannot escape the runs/ directory.
    assert p.parent == tmp_path / "runs"
    assert "/" not in p.name
    assert p.name.endswith(".events.jsonl")


def test_append_failure_is_silent(tmp_path, monkeypatch):
    # Root path points at a FILE — mkdir/open must fail, silently.
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(blocker))
    _reset_seq(monkeypatch)
    append_event("run1", "assistant_text", text="text")  # must not raise


def test_corrupt_lines_are_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(tmp_path))
    _reset_seq(monkeypatch)
    append_event("run1", "assistant_text", text="ok")
    with open(events_path("run1"), "a", encoding="utf-8") as fh:
        fh.write("not json\n")
    append_event("run1", "assistant_text", text="still ok")
    assert [e["text"] for e in read_events("run1", 0)] == ["ok", "still ok"]


# ── claude stream-json translation ───────────────────────────────────────────


def test_assistant_text_translates_verbatim():
    line = json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Reading tests…"}]}}
    )
    assert ClaudeStreamTranslator().translate(line) == [
        {"type": "assistant_text", "text": "Reading tests…"}
    ]


def test_tool_use_translates_with_name_and_input_preview():
    line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "pytest -q"}}
                ]
            },
        }
    )
    events = ClaudeStreamTranslator().translate(line)
    assert events[0]["type"] == "tool_use"
    assert events[0]["name"] == "Bash"
    assert "pytest -q" in events[0]["input"]


def test_tool_result_resolves_name_from_earlier_tool_use():
    t = ClaudeStreamTranslator()
    t.translate(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]
                },
            }
        )
    )
    events = t.translate(
        json.dumps(
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "t1",
                            "content": [{"type": "text", "text": "3 passed"}],
                            "is_error": False,
                        }
                    ]
                },
            }
        )
    )
    assert events == [
        {"type": "tool_result", "name": "Bash", "output": "3 passed", "is_error": False}
    ]


def test_result_event_translates_to_turn_end_with_usage():
    line = json.dumps(
        {"type": "result", "subtype": "success", "result": "done", "duration_ms": 1200, "num_turns": 4}
    )
    events = ClaudeStreamTranslator().translate(line)
    assert events[0]["type"] == "turn_end"
    assert events[0]["status"] == "success"
    assert events[0]["usage"] == {"duration_ms": 1200, "num_turns": 4}


def test_system_init_is_dropped():
    assert ClaudeStreamTranslator().translate(json.dumps({"type": "system", "subtype": "init"})) == []
    assert ClaudeStreamTranslator().translate("") == []


def test_non_json_lines_pass_through_as_assistant_text():
    events = ClaudeStreamTranslator().translate("plain CLI output\n")
    assert events == [{"type": "assistant_text", "text": "plain CLI output\n"}]


def test_mixed_text_and_tool_use_blocks_translate_in_order():
    line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Now running tests."},
                    {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "pytest"}},
                ]
            },
        }
    )
    events = ClaudeStreamTranslator().translate(line)
    assert [e["type"] for e in events] == ["assistant_text", "tool_use"]


# ── argv flag enforcement ────────────────────────────────────────────────────


def test_stream_json_flags_added_when_missing():
    argv = ensure_stream_json_flags(["claude", "-p", "hi"])
    assert argv[-4:] == [
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
    ]


def test_existing_output_format_is_respected():
    argv = ensure_stream_json_flags(["claude", "-p", "hi", "--output-format", "json"])
    assert argv.count("--output-format") == 1
    assert "stream-json" not in argv
    assert "--verbose" not in argv
    assert "--include-partial-messages" not in argv


def test_companion_flags_added_when_stream_json_present_without_them():
    argv = ensure_stream_json_flags(
        ["claude", "-p", "hi", "--output-format", "stream-json"]
    )
    assert argv[-2:] == ["--verbose", "--include-partial-messages"]
    argv2 = ensure_stream_json_flags(argv)
    assert argv2.count("--verbose") == 1  # idempotent
    assert argv2.count("--include-partial-messages") == 1


# ── partial-message token deltas (--include-partial-messages) ────────────────


def test_stream_event_text_delta_extracts_fragment():
    line = json.dumps(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "Rea"},
            },
            "session_id": "s1",
        }
    )
    assert stream_event_delta(line) == "Rea"


def test_stream_event_without_text_is_consumed_silently():
    # Not displayable, but still a stream_event: callers must skip the line
    # (return "") instead of translating/storing it.
    for event in (
        {"type": "message_start"},
        {"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": "{"}},
        {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "hm"}},
        {"type": "content_block_stop"},
    ):
        line = json.dumps({"type": "stream_event", "event": event})
        assert stream_event_delta(line) == ""


def test_non_stream_event_lines_return_none():
    assert stream_event_delta("") is None
    assert stream_event_delta("plain text") is None
    assert stream_event_delta(json.dumps({"type": "assistant", "message": {}})) is None
    # Content merely mentioning stream_event is not a stream_event line.
    assert (
        stream_event_delta(
            json.dumps({"type": "assistant", "note": 'about "stream_event" lines'})
        )
        is None
    )


def test_stream_events_do_not_reach_the_transcript_translator():
    line = json.dumps(
        {
            "type": "stream_event",
            "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "x"}},
        }
    )
    assert ClaudeStreamTranslator().translate(line) == []


def test_publish_delta_never_touches_the_events_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(tmp_path))
    _reset_seq(monkeypatch)
    run_events.publish_delta("run1", "tok")
    assert not events_path("run1").exists()
    assert read_events("run1", 0) == []


def test_transcript_route_is_mounted():
    from app import app

    schema = app.openapi()
    assert "/api/v1/runs/{uid}/transcript" in schema["paths"]
    assert "/api/v1/runs/{uid}/messages" in schema["paths"]
    assert "/api/v1/runs/{uid}/workspace/recreate" in schema["paths"]
    assert "/api/v1/sessions" not in schema["paths"]
    assert "/api/v1/executions" not in schema["paths"]
    ops = {
        op.get("operationId")
        for methods in schema["paths"].values()
        for op in methods.values()
        if isinstance(op, dict)
    }
    assert "opensweep_run_transcript" in ops


# ── structured tool-input previews (diff-capable tool cards) ─────────────────


def test_preview_structured_stays_json_parseable_when_truncating():
    from domains.investigations.services.run_events import preview_structured

    value = {"file_path": "a.py", "old_string": "x" * 50_000, "new_string": "y"}
    out = preview_structured(value, field_max=1_000)
    parsed = json.loads(out)  # must never be broken JSON
    assert parsed["file_path"] == "a.py"
    assert parsed["new_string"] == "y"
    assert len(parsed["old_string"]) == 1_000
    assert parsed["old_string"].endswith("…")


def test_preview_structured_handles_nested_containers():
    from domains.investigations.services.run_events import preview_structured

    value = {"edits": [{"old_string": "a" * 100, "new_string": "b"}], "n": 3}
    parsed = json.loads(preview_structured(value, field_max=10))
    assert parsed["n"] == 3
    assert parsed["edits"][0]["new_string"] == "b"
    assert len(parsed["edits"][0]["old_string"]) == 10


def test_preview_structured_falls_back_when_total_budget_exceeded():
    from domains.investigations.services.run_events import preview_structured

    value = {f"k{i}": "v" * 100 for i in range(50)}
    out = preview_structured(value, field_max=200, total_max=500)
    # Falls back to the compact preview — bounded, possibly not parseable.
    assert len(out) <= run_events.TOOL_PREVIEW_MAX_CHARS


def test_tool_use_input_is_json_parseable_for_edit_diffs():
    line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t9",
                        "name": "Edit",
                        "input": {
                            "file_path": "src/app.py",
                            "old_string": "def a():\n    pass\n" * 400,
                            "new_string": "def a():\n    return 1\n" * 400,
                        },
                    }
                ]
            },
        }
    )
    events = ClaudeStreamTranslator().translate(line)
    parsed = json.loads(events[0]["input"])
    assert parsed["file_path"] == "src/app.py"
    assert "old_string" in parsed and "new_string" in parsed
