"""Implement carry-over: what gets injected into the implement run."""

from domains.threads.services.thread_service import compose_addendum_for_thread


def _ev(text):
    return {"seq": 1, "ts": "", "turn": 1, "type": "user_message", "text": text}


def test_approved_plan_is_carried():
    out = compose_addendum_for_thread("approved", "## Plan\n1. X", [_ev("soft gate")])
    assert "## Plan" in out and "soft gate" in out


def test_drafted_plan_is_also_carried():
    # Soft gate: an unapproved draft still beats no plan.
    out = compose_addendum_for_thread("drafted", "## Plan\n1. X", [])
    assert "## Plan" in out


def test_no_plan_no_conversation_gives_empty_addendum():
    assert compose_addendum_for_thread("none", "", []) == ""


def test_conversation_carried_even_without_plan():
    out = compose_addendum_for_thread("none", "", [_ev("use redis pub/sub")])
    assert "use redis pub/sub" in out
