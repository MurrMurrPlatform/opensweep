"""P0 — freshness core, against the real test Neo4j (localhost:7999).

Exercises the closed freshness loop end-to-end with real Doc/Area nodes:
  push (mark stale) → derived stale badge true → confirm → stale badge false.

Covers `mark_docs_stale`, `confirm_doc_current`, `confirm_area_current`, the
stale_paths dedupe + cap, non-matching isolation, per-doc error isolation, and
archived-doc exclusion from listings / watch-scans / mark_docs_stale.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from domains.areas.models import Area, area_is_stale
from domains.areas.services.area_freshness import (
    confirm_area_current,
    mark_areas_stale,
)
from domains.docs.models import Doc, doc_is_stale
from domains.docs.services.doc_freshness import (
    confirm_doc_current,
    docs_watching_paths,
    mark_docs_stale,
)
from domains.docs.services.doc_service import list_docs
from domains.repositories.services.path_matching import MAX_STALE_PATHS

pytestmark = pytest.mark.integration


def _repo() -> str:
    return "repo-" + uuid4().hex[:8]


async def _make_doc(
    repo: str,
    slug: str,
    watch_paths: list[str],
    *,
    archived: bool = False,
    reviewed: datetime | None = None,
) -> Doc:
    d = Doc(
        uid=uuid4().hex,
        repository_uid=repo,
        slug=slug,
        watch_paths=list(watch_paths),
        archived=archived,
        last_reviewed_at=reviewed,
    )
    await d.save()
    return d


async def _make_area(
    repo: str, key: str, scope_paths: list[str], *, kind: str = "subsystem"
) -> Area:
    a = Area(
        uid=uuid4().hex,
        repository_uid=repo,
        key=key,
        kind=kind,
        scope_paths=list(scope_paths),
    )
    await a.save()
    return a


# ── mark_docs_stale ─────────────────────────────────────────────────────────


async def test_mark_docs_stale_stamps_matching_and_leaves_others():
    repo = _repo()
    watcher = await _make_doc(repo, "backend/api", ["back_end/api"])
    bystander = await _make_doc(repo, "frontend", ["front_end/src"])

    result = await mark_docs_stale(repo, ["back_end/api/v1/runs.py"])

    assert result.docs_marked == 1
    assert result.errors == []

    watcher = await Doc.nodes.get(uid=watcher.uid)
    bystander = await Doc.nodes.get(uid=bystander.uid)
    assert watcher.code_changed_at is not None
    assert watcher.stale_paths == ["back_end/api/v1/runs.py"]
    assert bystander.code_changed_at is None
    assert bystander.stale_paths == []


async def test_mark_docs_stale_dedupes_and_caps_stale_paths():
    repo = _repo()
    d = await _make_doc(repo, "backend", ["src"])

    # First push: a batch of matching paths, one repeated.
    first = [f"src/f{i}.py" for i in range(50)] + ["src/f0.py"]
    await mark_docs_stale(repo, first)
    # Second push overlaps the first (dedupe) and adds well past the cap.
    second = [f"src/f{i}.py" for i in range(40, 40 + MAX_STALE_PATHS + 50)]
    await mark_docs_stale(repo, second)

    d = await Doc.nodes.get(uid=d.uid)
    assert len(d.stale_paths) == MAX_STALE_PATHS  # capped
    assert len(d.stale_paths) == len(set(d.stale_paths))  # deduped


async def test_mark_docs_stale_error_isolation(monkeypatch):
    """One doc whose save() explodes must not block the others."""
    repo = _repo()
    good = await _make_doc(repo, "good", ["src"])
    bad = await _make_doc(repo, "bad", ["src"])

    original_save = Doc.save

    async def flaky_save(self, *args, **kwargs):
        if self.uid == bad.uid:
            raise RuntimeError("boom")
        return await original_save(self, *args, **kwargs)

    monkeypatch.setattr(Doc, "save", flaky_save, raising=True)

    result = await mark_docs_stale(repo, ["src/x.py"])

    assert result.docs_marked == 1  # only the good one
    assert len(result.errors) == 1
    assert bad.uid in result.errors[0]

    monkeypatch.setattr(Doc, "save", original_save, raising=True)
    good = await Doc.nodes.get(uid=good.uid)
    assert good.code_changed_at is not None


# ── confirm_doc_current / confirm_area_current ──────────────────────────────


async def test_confirm_doc_current_clears_stale_and_advances_review():
    repo = _repo()
    d = await _make_doc(repo, "backend/api", ["back_end/api"])
    await mark_docs_stale(repo, ["back_end/api/runs.py"])

    before = datetime.now(UTC)
    confirmed = await confirm_doc_current(repo, "backend/api")

    assert confirmed is not None
    assert confirmed.stale_paths == []
    assert confirmed.last_reviewed_at is not None
    assert confirmed.last_reviewed_at >= before


async def test_confirm_doc_current_unknown_slug_returns_none():
    repo = _repo()
    assert await confirm_doc_current(repo, "does/not/exist") is None


async def test_confirm_area_current_clears_stale_and_advances_review():
    repo = _repo()
    a = await _make_area(repo, "backend", ["back_end"])
    await mark_areas_stale(repo, ["back_end/app.py"])

    before = datetime.now(UTC)
    confirmed = await confirm_area_current(repo, "backend")

    assert confirmed is not None
    assert confirmed.stale_paths == []
    assert confirmed.last_reviewed_at is not None
    assert confirmed.last_reviewed_at >= before


async def test_confirm_area_current_unknown_key_returns_none():
    repo = _repo()
    assert await confirm_area_current(repo, "no-such-area") is None


# ── End-to-end freshness loop ───────────────────────────────────────────────


async def test_doc_freshness_loop_push_stale_confirm_fresh():
    repo = _repo()
    # Reviewed in the past so a later push cleanly makes it stale.
    d = await _make_doc(
        repo,
        "backend/api",
        ["back_end/api"],
        reviewed=datetime.now(UTC) - timedelta(days=1),
    )
    assert doc_is_stale(await Doc.nodes.get(uid=d.uid)) is False

    await mark_docs_stale(repo, ["back_end/api/v1/runs.py"])
    assert doc_is_stale(await Doc.nodes.get(uid=d.uid)) is True

    await confirm_doc_current(repo, "backend/api")
    assert doc_is_stale(await Doc.nodes.get(uid=d.uid)) is False


async def test_area_freshness_loop_push_stale_confirm_fresh():
    repo = _repo()
    a = await _make_area(repo, "backend", ["back_end"])
    # Area has no last_reviewed_at initially; set one in the past.
    a.last_reviewed_at = datetime.now(UTC) - timedelta(days=1)
    await a.save()
    assert area_is_stale(await Area.nodes.get(uid=a.uid)) is False

    await mark_areas_stale(repo, ["back_end/app.py"])
    assert area_is_stale(await Area.nodes.get(uid=a.uid)) is True

    await confirm_area_current(repo, "backend")
    assert area_is_stale(await Area.nodes.get(uid=a.uid)) is False


# ── Archived docs excluded everywhere ───────────────────────────────────────


async def test_archived_docs_excluded_from_list_watch_and_mark():
    repo = _repo()
    live = await _make_doc(repo, "live", ["src"])
    archived = await _make_doc(repo, "old", ["src"], archived=True)

    # list_docs excludes archived.
    slugs = {d.slug for d in await list_docs(repo)}
    assert "live" in slugs
    assert "old" not in slugs

    # docs_watching_paths excludes archived.
    watching = await docs_watching_paths(repo, ["src/thing.py"])
    assert live.uid in watching
    assert archived.uid not in watching

    # mark_docs_stale excludes archived — only the live doc is marked.
    result = await mark_docs_stale(repo, ["src/thing.py"])
    assert result.docs_marked == 1
    archived = await Doc.nodes.get(uid=archived.uid)
    assert archived.code_changed_at is None
