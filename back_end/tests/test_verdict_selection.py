"""Verdict selection for the convergence predicate (pure — pick_latest_verdict).

A late-FINISHING review of an OLD sha must never displace a fresh approve of
the current head: verdicts at head are preferred regardless of creation time.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

from domains.delivery.services.pull_request_service import pick_latest_verdict

HEAD = "a" * 40
OLD = "b" * 40


def _v(uid, sha, minutes):
    return SimpleNamespace(
        uid=uid, sha=sha, created_at=datetime(2026, 7, 9, 12, minutes, tzinfo=UTC)
    )


def test_empty_returns_none():
    assert pick_latest_verdict([], head_sha=HEAD) is None


def test_single_verdict_wins():
    v = _v("v1", HEAD, 0)
    assert pick_latest_verdict([v], head_sha=HEAD) is v


def test_late_stale_review_cannot_displace_fresh_approve():
    # The bug: a review of the OLD sha finishes AFTER the approve of head.
    fresh_approve = _v("approve", HEAD, minutes=0)
    late_stale = _v("stale", OLD, minutes=30)
    assert pick_latest_verdict([fresh_approve, late_stale], head_sha=HEAD) is fresh_approve
    # Order independence.
    assert pick_latest_verdict([late_stale, fresh_approve], head_sha=HEAD) is fresh_approve


def test_latest_at_head_wins_among_head_verdicts():
    first = _v("v1", HEAD, minutes=0)
    second = _v("v2", HEAD, minutes=5)
    assert pick_latest_verdict([first, second], head_sha=HEAD) is second


def test_falls_back_to_all_verdicts_when_none_match_head():
    old_a = _v("v1", OLD, minutes=0)
    old_b = _v("v2", OLD, minutes=5)
    # No verdict at head → the latest overall is returned (the predicate then
    # flags it stale — but "stale verdict" beats "no verdict" for reporting).
    assert pick_latest_verdict([old_a, old_b], head_sha=HEAD) is old_b


def test_without_head_sha_latest_overall_wins():
    a = _v("v1", OLD, minutes=0)
    b = _v("v2", HEAD, minutes=5)
    assert pick_latest_verdict([a, b], head_sha="") is b


def test_created_at_tie_breaks_on_uid_desc():
    a = _v("aaaa", HEAD, minutes=0)
    b = _v("bbbb", HEAD, minutes=0)
    assert pick_latest_verdict([a, b], head_sha=HEAD) is b
    assert pick_latest_verdict([b, a], head_sha=HEAD) is b


def test_missing_created_at_sorts_last():
    dated = _v("v1", HEAD, minutes=0)
    undated = SimpleNamespace(uid="v0", sha=HEAD, created_at=None)
    assert pick_latest_verdict([undated, dated], head_sha=HEAD) is dated
