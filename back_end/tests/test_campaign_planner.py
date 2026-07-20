"""Campaign planner — pure partition + template math."""

from datetime import UTC, datetime, timedelta

from domains.campaigns.services.planner import build_plan, normalize_areas

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _doc(uid, watch, *, title=""):
    return {"uid": uid, "slug": uid, "title": title or uid, "watch_paths": watch}


def _lens(key, *, scope="local", global_agent_key="", enabled=True):
    return {
        "key": key,
        "scope": scope,
        "global_agent_key": global_agent_key,
        "enabled": enabled,
    }


LENSES = [
    _lens("bugs"),
    _lens("security"),
    _lens("architecture-review", scope="global", global_agent_key="architecture-review"),
]


# ── normalize_areas ──────────────────────────────────────────────────────────


def test_right_sized_area_stays_whole():
    paths = [f"src/api/f{i}.py" for i in range(60)]
    areas = normalize_areas([_doc("d1", ["src/api"])], paths)
    assert len(areas) == 1
    assert areas[0]["scope_paths"] == ["src/api"]
    assert areas[0]["doc_uids"] == ["d1"]
    assert areas[0]["file_count"] == 60


def test_oversized_area_splits_by_first_level_subdir():
    paths = [f"src/a/f{i}.py" for i in range(100)] + [f"src/b/f{i}.py" for i in range(100)]
    areas = normalize_areas([_doc("d1", ["src"], title="Source")], paths)
    assert len(areas) == 2
    assert {tuple(a["scope_paths"]) for a in areas} == {("src/a",), ("src/b",)}
    for a in areas:
        assert a["doc_uids"] == ["d1"]
        assert a["title"].startswith("Source — ")
        assert a["file_count"] == 100


def test_adjacent_tiny_areas_merge():
    paths = [f"a/f{i}.py" for i in range(10)] + [f"b/f{i}.py" for i in range(10)]
    areas = normalize_areas(
        [_doc("d1", ["a"]), _doc("d2", ["b"])], paths, target_min=15, target_max=150
    )
    assert len(areas) == 1
    assert areas[0]["scope_paths"] == ["a", "b"]
    assert areas[0]["doc_uids"] == ["d1", "d2"]
    assert areas[0]["file_count"] == 20
    assert " + " in areas[0]["title"]


def test_unwatched_paths_land_in_remainder():
    paths = ["src/f.py", "scripts/x.sh", "scripts/y.sh", "README.md"]
    areas = normalize_areas([_doc("d1", ["src"])], paths, target_min=1)
    remainder = [a for a in areas if a["title"] == "Uncovered paths"]
    assert len(remainder) == 1
    assert remainder[0]["doc_uids"] == []
    assert remainder[0]["file_count"] == 3
    assert set(remainder[0]["scope_paths"]) == {"scripts", "README.md"}


def test_oversized_remainder_splits_too():
    paths = [f"x/f{i}.py" for i in range(100)] + [f"y/f{i}.py" for i in range(100)]
    areas = normalize_areas([_doc("d1", ["src"])], paths, target_min=10, target_max=150)
    remainders = [a for a in areas if a["title"].startswith("Uncovered paths")]
    assert len(remainders) == 2
    assert {tuple(a["scope_paths"]) for a in remainders} == {("x",), ("y",)}


def test_empty_tree_degrades_to_one_part_per_doc():
    areas = normalize_areas([_doc("d1", ["src"]), _doc("d2", ["lib"])], [])
    assert len(areas) == 2
    assert all(a["file_count"] is None for a in areas)
    # No remainder can exist without a tree.
    assert all(a["title"] != "Uncovered paths" for a in areas)


def test_docs_without_watch_paths_are_skipped():
    assert normalize_areas([_doc("d1", [])], []) == []


# ── build_plan templates ─────────────────────────────────────────────────────


def _areas(n):
    return [
        {"title": f"a{i}", "scope_paths": [f"a{i}"], "doc_uids": [f"d{i}"], "file_count": 60}
        for i in range(n)
    ]


def test_full_plan_covers_all_areas_plus_globals():
    parts = build_plan("full", _areas(3), LENSES)
    areas = [p for p in parts if p["kind"] == "area"]
    globals_ = [p for p in parts if p["kind"] == "global"]
    assert len(areas) == 3 and len(globals_) == 1
    assert all(p["lens_keys"] == ["bugs", "security"] for p in areas)
    assert globals_[0]["lens_keys"] == ["architecture-review"]
    # idx sequential, areas before globals, all pending.
    assert [p["idx"] for p in parts] == list(range(4))
    assert all(p["state"] == "pending" and p["run_uid"] == "" for p in parts)


def test_disabled_lenses_are_excluded():
    lenses = [_lens("bugs"), _lens("security", enabled=False)]
    parts = build_plan("full", _areas(1), lenses)
    assert parts[0]["lens_keys"] == ["bugs"]


def test_rotation_picks_least_recently_covered_never_covered_first():
    recency = {
        "a0/f.py": NOW - timedelta(days=1),  # freshest
        "a1/f.py": NOW - timedelta(days=30),  # stalest covered
        # a2 never covered
    }
    parts = build_plan("rotation", _areas(3), LENSES, k=2, path_recency=recency)
    assert [p["title"] for p in parts] == ["a2", "a1"]
    assert all(p["kind"] == "area" for p in parts)  # no globals in rotation


def test_rotation_without_recency_takes_first_k():
    parts = build_plan("rotation", _areas(5), LENSES, k=3)
    assert [p["title"] for p in parts] == ["a0", "a1", "a2"]


def test_focused_uses_only_the_focus_lens():
    parts = build_plan("focused", _areas(2), LENSES, focus_lens="security")
    assert all(p["lens_keys"] == ["security"] for p in parts)
    assert all(p["kind"] == "area" for p in parts)  # security has no global part


def test_focused_on_a_global_lens_adds_its_sweep():
    parts = build_plan("focused", _areas(2), LENSES, focus_lens="architecture-review")
    globals_ = [p for p in parts if p["kind"] == "global"]
    assert len(globals_) == 1
    assert globals_[0]["lens_keys"] == ["architecture-review"]
    assert globals_[0]["idx"] == 2  # after the areas
