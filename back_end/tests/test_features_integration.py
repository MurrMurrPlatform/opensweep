"""P1 — feature-leaf spec target selection (Phase 1B), against the real test
Neo4j (localhost:7999).

`feature_leaf_spec_targets` is the pure selection helper behind
`run_generate_specs`: it picks the enabled feature LEAVES that lack a spec or
whose spec went stale, and excludes parent-grouping features. Tested against
real Area nodes without dispatching a run.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from domains.areas.models import Area
from domains.runs.services.sweep import feature_leaf_spec_targets

pytestmark = pytest.mark.integration


def _repo() -> str:
    return "repo-" + uuid4().hex[:8]


async def _make_area(
    repo: str,
    key: str,
    *,
    kind: str = "feature",
    enabled: bool = True,
    spec: str = "",
    stale: bool = False,
) -> Area:
    a = Area(
        uid=uuid4().hex,
        repository_uid=repo,
        key=key,
        kind=kind,
        enabled=enabled,
        spec=spec,
        scope_paths=["src"],
    )
    await a.save()
    if stale:
        # code moved after the last review → area_is_stale True.
        a.last_reviewed_at = datetime.now(UTC) - timedelta(days=1)
        a.code_changed_at = datetime.now(UTC)
        await a.save()
    else:
        a.last_reviewed_at = datetime.now(UTC)
        await a.save()
    return a


async def test_selects_no_spec_and_stale_leaves():
    repo = _repo()
    no_spec = await _make_area(repo, "feature/checkout", spec="")
    stale = await _make_area(repo, "feature/search", spec="has spec", stale=True)
    # Current leaf with a spec — not a target.
    await _make_area(repo, "feature/billing", spec="has spec", stale=False)

    targets = await feature_leaf_spec_targets(repo)
    keys = {a.key for a in targets}

    assert keys == {no_spec.key, stale.key}


async def test_excludes_parent_grouping_features():
    repo = _repo()
    # "feature/auth" is a parent grouping — a child leaf nests under it, so it
    # is NOT a leaf and never a spec target even though it has no spec.
    parent = await _make_area(repo, "feature/auth", spec="")
    leaf = await _make_area(repo, "feature/auth/oauth", spec="")

    targets = await feature_leaf_spec_targets(repo)
    keys = {a.key for a in targets}

    assert leaf.key in keys
    assert parent.key not in keys


async def test_excludes_non_feature_and_disabled_areas():
    repo = _repo()
    # A subsystem leaf with no spec — not a feature, so ignored.
    await _make_area(repo, "backend/api", kind="subsystem", spec="")
    # A disabled feature leaf with no spec — ignored.
    await _make_area(repo, "feature/legacy", enabled=False, spec="")
    # An enabled feature leaf with no spec — the only target.
    target = await _make_area(repo, "feature/live", spec="")

    targets = await feature_leaf_spec_targets(repo)
    keys = {a.key for a in targets}

    assert keys == {target.key}


async def test_repo_isolation_and_stable_sort():
    repo = _repo()
    other = _repo()
    await _make_area(other, "feature/zzz", spec="")  # different repo — excluded
    b = await _make_area(repo, "feature/bbb", spec="")
    a = await _make_area(repo, "feature/aaa", spec="")

    targets = await feature_leaf_spec_targets(repo)
    keys = [t.key for t in targets]

    assert keys == sorted(keys)  # sorted by key
    assert set(keys) == {a.key, b.key}
