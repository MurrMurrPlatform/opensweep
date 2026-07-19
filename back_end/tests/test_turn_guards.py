"""Follow-up message guard (turn_service.ensure_can_send) — pure, no Neo4j.

First-message queueing: a queued CHAT run accepts the message (run_turn holds
it until the background workspace clone finishes); every other queued/running
run still 409s.
"""

import pytest
from fastapi import HTTPException

from domains.investigations.services.turn_service import ensure_can_send


def _detail(exc_info) -> str:
    return str(exc_info.value.detail)


def test_follow_up_statuses_accept_messages():
    for status in ("awaiting_input", "ended", "failed", "cancelled", "limit_exceeded"):
        ensure_can_send(status, False)  # must not raise


def test_in_flight_always_409s_even_for_queued_chat():
    with pytest.raises(HTTPException) as exc_info:
        ensure_can_send("queued", True, playbook="chat")
    assert exc_info.value.status_code == 409
    assert "in flight" in _detail(exc_info)


def test_queued_chat_run_accepts_the_message():
    ensure_can_send("queued", False, playbook="chat")  # must not raise


def test_queued_non_chat_runs_still_409():
    for playbook in ("", "ask", "review", "fix", "implement", "verify"):
        with pytest.raises(HTTPException) as exc_info:
            ensure_can_send("queued", False, playbook=playbook)
        assert exc_info.value.status_code == 409


def test_running_chat_run_still_409s():
    # Queueing applies to workspace prep only — a chat run mid-turn is busy.
    with pytest.raises(HTTPException) as exc_info:
        ensure_can_send("running", False, playbook="chat")
    assert exc_info.value.status_code == 409


def test_paused_quota_409s_with_resume_hint():
    with pytest.raises(HTTPException) as exc_info:
        ensure_can_send("paused_quota", False, playbook="chat")
    assert "quota" in _detail(exc_info)


# ── needs_input consumption ──────────────────────────────────────────────────


def test_follow_up_turn_consumes_needs_input():
    from domains.investigations.services.turn_service import consume_needs_input

    # The user replying IS the input the run was waiting on — the flag set by
    # ask_user must not survive into the next turn.
    assert consume_needs_input({"needs_input": True, "other": 1}) == {"other": 1}
    assert consume_needs_input({}) == {}
    assert consume_needs_input(None) == {}
