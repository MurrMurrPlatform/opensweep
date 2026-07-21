"""Staleness-driven audit target ranking (§F) — pure."""

from datetime import UTC, datetime, timedelta

from domains.runs.services.audit_selection import PageInfo, path_recency, rank_targets

NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


def _page(
    uid, *, has_body=True, created=None, changed=None, checked=None, reviewed=None
):
    # `checked` = latest Checked stamp (audit-coverage axis: gates
    # never-checked). `reviewed` = last_reviewed_at (the single staleness
    # axis: code_changed_at > last_reviewed_at). A stale page is one that has
    # been audited (checked) but whose code moved past its last review.
    return PageInfo(
        doc_uid=uid,
        slug=uid,
        has_body=has_body,
        created_at=created or NOW - timedelta(days=30),
        code_changed_at=changed,
        last_reviewed_at=reviewed,
        last_checked=checked,
    )


def test_never_checked_pages_come_first_oldest_first():
    pages = [
        _page("young-unchecked", created=NOW - timedelta(days=1)),
        _page(
            "stale",
            changed=NOW,
            checked=NOW - timedelta(days=2),
            reviewed=NOW - timedelta(days=2),
        ),
        _page("old-unchecked", created=NOW - timedelta(days=90)),
    ]
    out = rank_targets(pages, limit=10)
    assert [t.doc_uid for t in out] == ["old-unchecked", "young-unchecked", "stale"]
    assert out[0].reason == "never-checked"
    assert out[2].reason == "stale"


def test_stale_pages_ordered_by_stalest_review():
    pages = [
        _page(
            "recently-reviewed",
            changed=NOW,
            checked=NOW - timedelta(days=1),
            reviewed=NOW - timedelta(days=1),
        ),
        _page(
            "long-ago-reviewed",
            changed=NOW,
            checked=NOW - timedelta(days=30),
            reviewed=NOW - timedelta(days=30),
        ),
    ]
    out = rank_targets(pages, limit=10)
    assert [t.doc_uid for t in out] == ["long-ago-reviewed", "recently-reviewed"]


def test_fresh_and_empty_pages_are_never_targets():
    pages = [
        # reviewed after the change → fresh (badge agrees), though audited earlier.
        _page(
            "fresh",
            changed=NOW - timedelta(days=5),
            checked=NOW,
            reviewed=NOW,
        ),
        _page(
            "never-changed", checked=NOW - timedelta(days=90), reviewed=NOW - timedelta(days=90)
        ),  # no code movement
        _page("empty-shell", has_body=False),  # bootstrap conventions stub
    ]
    assert rank_targets(pages, limit=10) == []


def test_limit_truncates_and_zero_is_safe():
    pages = [_page(f"p{i}") for i in range(5)]
    assert len(rank_targets(pages, limit=2)) == 2
    assert rank_targets(pages, limit=0) == []


# ── path_recency (campaign rotation input) ───────────────────────────────────


def _stamp(paths, *, checked, outcome="clean"):
    return {"covered_paths": paths, "checked_at": checked, "outcome": outcome}


def test_path_recency_keeps_the_latest_stamp_per_exact_path():
    old, new = NOW - timedelta(days=10), NOW - timedelta(days=1)
    out = path_recency(
        [
            _stamp(["a.py", "b.py"], checked=old),
            _stamp(["b.py"], checked=new, outcome="findings"),
        ]
    )
    assert out == {"a.py": old, "b.py": new}


def test_path_recency_ignores_failed_stamps():
    out = path_recency(
        [
            _stamp(["a.py"], checked=NOW, outcome="failed"),
            _stamp(["b.py"], checked=NOW - timedelta(days=5)),
        ]
    )
    assert out == {"b.py": NOW - timedelta(days=5)}


def test_path_recency_skips_stamps_without_a_timestamp():
    assert path_recency([_stamp(["a.py"], checked=None)]) == {}
    assert path_recency([]) == {}
