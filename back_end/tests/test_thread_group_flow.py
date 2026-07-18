"""Group flow (Phase 5): one thread on the parent → one PR covers the batch."""

from types import SimpleNamespace

from domains.threads.services.intents import build_group_addendum


def _child(uid, title, desc="", ac=None):
    return SimpleNamespace(
        uid=uid, title=title, description=desc, acceptance_criteria=ac or []
    )


def test_no_children_no_addendum():
    assert build_group_addendum([]) == ""


def test_children_are_listed_with_acceptance():
    out = build_group_addendum(
        [
            _child("c-1", "Fix login", "500 on login", ["login works"]),
            _child("c-2", "Fix logout"),
        ]
    )
    assert "ALL subtickets" in out
    assert "c-1" in out and "Fix login" in out and "login works" in out
    assert "c-2" in out and "(no description)" in out


def test_long_descriptions_truncate():
    out = build_group_addendum([_child("c-1", "T", "x" * 1000)])
    assert "…" in out and len(out) < 900
