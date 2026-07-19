"""Staleness-driven audit target ranking (§F) — pure."""

from datetime import UTC, datetime, timedelta

from domains.runs.services.audit_selection import PageInfo, rank_targets

NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


def _page(uid, *, has_body=True, created=None, changed=None, checked=None):
    return PageInfo(
        doc_uid=uid,
        slug=uid,
        has_body=has_body,
        created_at=created or NOW - timedelta(days=30),
        code_changed_at=changed,
        last_checked=checked,
    )


def test_never_checked_pages_come_first_oldest_first():
    pages = [
        _page("young-unchecked", created=NOW - timedelta(days=1)),
        _page("stale", changed=NOW, checked=NOW - timedelta(days=2)),
        _page("old-unchecked", created=NOW - timedelta(days=90)),
    ]
    out = rank_targets(pages, limit=10)
    assert [t.doc_uid for t in out] == ["old-unchecked", "young-unchecked", "stale"]
    assert out[0].reason == "never-checked"
    assert out[2].reason == "code-changed-since-check"


def test_stale_pages_ordered_by_stalest_check():
    pages = [
        _page("recently-checked", changed=NOW, checked=NOW - timedelta(days=1)),
        _page("long-ago-checked", changed=NOW, checked=NOW - timedelta(days=30)),
    ]
    out = rank_targets(pages, limit=10)
    assert [t.doc_uid for t in out] == ["long-ago-checked", "recently-checked"]


def test_fresh_and_empty_pages_are_never_targets():
    pages = [
        _page("fresh", changed=NOW - timedelta(days=5), checked=NOW),  # checked after change
        _page("never-changed", checked=NOW - timedelta(days=90)),  # no code movement
        _page("empty-shell", has_body=False),  # bootstrap conventions stub
    ]
    assert rank_targets(pages, limit=10) == []


def test_limit_truncates_and_zero_is_safe():
    pages = [_page(f"p{i}") for i in range(5)]
    assert len(rank_targets(pages, limit=2)) == 2
    assert rank_targets(pages, limit=0) == []
