"""Codex transcript-tail continuation pass (Task 7).

Pure tests for codex_continuation_prompt — no Neo4j, no I/O, no CLI.
"""

import json

from domains.executors.cli_tracking import (
    _codex_delta_feeder,
    codex_continuation_prompt,
    envelope_has_complete_run,
)


def test_continuation_prompt_embeds_tail_and_nudge():
    out = codex_continuation_prompt("CONTINUE NOW", "assistant: found 3 issues so far")
    assert "CONTINUE NOW" in out
    assert "found 3 issues so far" in out
    assert "no session resume" in out


def test_envelope_has_complete_run_true_when_present():
    envelope = {
        "summary": "done",
        "tool_calls": [
            {"tool": "create_finding", "args": {}},
            {"tool": "complete_run", "args": {"summary": "wrapped up"}},
        ],
    }
    assert envelope_has_complete_run(envelope) is True


def test_envelope_has_complete_run_false_without_entry():
    envelope = {"summary": "still going", "tool_calls": [{"tool": "create_finding", "args": {}}]}
    assert envelope_has_complete_run(envelope) is False


def test_envelope_has_complete_run_false_on_none():
    assert envelope_has_complete_run(None) is False


def test_envelope_has_complete_run_false_on_empty_dict():
    assert envelope_has_complete_run({}) is False


# ── _codex_delta_feeder: run-path streaming parity with the turn path ─────────
# on_chunk gets the running TOTAL each tick. The feeder must surface only
# agent_message text from codex's `exec --json` JSONL, never the raw events —
# dumping the raw stream is what put `{"type":"thread.started"}` lines in the UI.

_THREAD = '{"type":"thread.started","thread_id":"t1"}'
_TURN = '{"type":"turn.started"}'


def _agent_msg(text):
    return json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": text}})


def test_feeder_filters_raw_events_and_yields_agent_message():
    feed = _codex_delta_feeder()
    total = f"{_THREAD}\n{_TURN}\n{_agent_msg('Mapping the repo.')}\n"
    assert feed(total) == ["Mapping the repo."]


def test_feeder_ignores_raw_events_entirely():
    feed = _codex_delta_feeder()
    assert feed(f"{_THREAD}\n{_TURN}\n") == []


def test_feeder_buffers_partial_line_across_chunks():
    feed = _codex_delta_feeder()
    msg = _agent_msg("Hello world")
    total = f"{_THREAD}\n"
    assert feed(total) == []  # only the raw event so far
    total += msg[:15]  # agent_message line arrives split, no newline yet
    assert feed(total) == []  # incomplete line held back, not emitted raw
    total += msg[15:] + "\n"
    assert feed(total) == ["Hello world"]


def test_feeder_emits_each_agent_message_once():
    feed = _codex_delta_feeder()
    total = f"{_agent_msg('first')}\n"
    assert feed(total) == ["first"]
    # Next tick's running total includes the already-emitted line — not repeated.
    total += f"{_agent_msg('second')}\n"
    assert feed(total) == ["second"]


def test_feeder_handles_legacy_msg_shape():
    feed = _codex_delta_feeder()
    line = json.dumps({"msg": {"type": "agent_message", "message": "legacy text"}})
    assert feed(line + "\n") == ["legacy text"]
