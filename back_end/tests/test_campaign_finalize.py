"""build_summary — the pure campaign digest."""

from domains.campaigns.services.finalize import build_summary


def _part(idx, *, state="done", covered=0, skipped=0, title=""):
    return {
        "idx": idx,
        "kind": "area",
        "title": title or f"p{idx}",
        "scope_paths": [f"p{idx}"],
        "state": state,
        "covered": covered,
        "skipped": skipped,
    }


def test_counts_by_severity_and_part():
    parts = [_part(0), _part(1)]
    findings = {
        0: [
            {"severity": "high", "tags": [], "title": "a"},
            {"severity": "low", "tags": [], "title": "b"},
        ],
        1: [{"severity": "high", "tags": [], "title": "c"}],
    }
    summary = build_summary(parts, findings, [])
    assert summary["counts"]["total"] == 3
    assert summary["counts"]["by_severity"] == {"high": 2, "low": 1}
    assert summary["counts"]["by_part"] == {"0": 2, "1": 1}


def test_coverage_rows_carry_part_state_and_counts():
    parts = [_part(0, covered=12, skipped=3), _part(1, state="failed")]
    summary = build_summary(parts, {}, ["p1"])
    rows = summary["coverage"]["parts"]
    assert rows[0] == {"idx": 0, "title": "p0", "covered": 12, "skipped": 3, "state": "done"}
    assert rows[1]["state"] == "failed"
    assert summary["coverage"]["holes"] == ["p1"]


def test_failed_parts_listed_sorted():
    parts = [_part(2, state="failed"), _part(0, state="failed"), _part(1)]
    summary = build_summary(parts, {}, [])
    assert summary["failed_parts"] == [0, 2]


def test_missing_severity_defaults_to_medium():
    summary = build_summary([_part(0)], {0: [{"tags": [], "title": "x"}]}, [])
    assert summary["counts"]["by_severity"] == {"medium": 1}


def test_empty_campaign_summary_shape():
    summary = build_summary([], {}, [])
    assert summary["counts"] == {"by_severity": {}, "by_part": {}, "total": 0}
    assert summary["coverage"] == {"parts": [], "holes": []}
    assert summary["failed_parts"] == []
