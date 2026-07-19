"""Codex transcript-tail continuation pass (Task 7).

Pure tests for codex_continuation_prompt — no Neo4j, no I/O, no CLI.
"""

from domains.executors.cli_tracking import codex_continuation_prompt


def test_continuation_prompt_embeds_tail_and_nudge():
    out = codex_continuation_prompt("CONTINUE NOW", "assistant: found 3 issues so far")
    assert "CONTINUE NOW" in out
    assert "found 3 issues so far" in out
    assert "no session resume" in out
