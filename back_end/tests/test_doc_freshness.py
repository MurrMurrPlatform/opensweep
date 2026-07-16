"""Pure-Python tests for doc freshness (KNOWLEDGE_V3_DOCUMENTATION §9).

The webhook-driven mark_docs_stale flow is DB-bound (integration tests);
here we pin the pure pieces: path matching and the derived stale rule.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from domains.docs.models import doc_is_stale
from domains.docs.services import doc_freshness
from domains.docs.services.doc_freshness import docs_watching_paths, watches_path


def test_watches_path_matches_exact_and_nested():
    assert watches_path(["back_end/domains"], "back_end/domains")
    assert watches_path(["back_end/domains"], "back_end/domains/docs/models.py")
    assert not watches_path(["back_end/domains"], "back_end/domains2/models.py")
    assert not watches_path(["back_end/domains"], "front_end/src/App.vue")


def test_watches_path_normalizes_slashes_and_dots():
    assert watches_path(["./back_end/domains/"], "back_end/domains/docs/models.py")
    assert not watches_path([""], "anything.py")
    assert not watches_path([], "anything.py")


def _doc(code_changed_at=None, last_reviewed_at=None):
    return SimpleNamespace(
        code_changed_at=code_changed_at, last_reviewed_at=last_reviewed_at
    )


def _watch_doc(uid, repository_uid, watch_paths):
    return SimpleNamespace(
        uid=uid, repository_uid=repository_uid, watch_paths=watch_paths
    )


async def test_docs_watching_paths_returns_empty_for_no_paths():
    # Guard runs before any DB access — safe without a fake store.
    assert await docs_watching_paths("repo-1", []) == []
    assert await docs_watching_paths("repo-1", ["  ", ""]) == []


async def test_docs_watching_paths_matches_only_watching_docs_in_repo(monkeypatch):
    docs = [
        _watch_doc("d-queue", "repo-1", ["back_end/domains/delivery"]),
        _watch_doc("d-docs", "repo-1", ["back_end/domains/docs"]),
        _watch_doc("d-other-repo", "repo-2", ["back_end/domains/delivery"]),
        _watch_doc("d-no-watch", "repo-1", []),
    ]

    class _Nodes:
        @staticmethod
        async def all():
            return docs

    monkeypatch.setattr(doc_freshness, "Doc", SimpleNamespace(nodes=_Nodes))

    hits = await docs_watching_paths(
        "repo-1", ["back_end/domains/delivery/services/fix_run_service.py"]
    )
    assert hits == ["d-queue"]  # right repo, watching path; others excluded


def test_stale_is_derived_from_change_vs_review():
    now = datetime.now(UTC)
    assert not doc_is_stale(_doc())  # never touched
    assert doc_is_stale(_doc(code_changed_at=now))  # changed, never reviewed
    assert doc_is_stale(
        _doc(code_changed_at=now, last_reviewed_at=now - timedelta(hours=1))
    )
    assert not doc_is_stale(
        _doc(code_changed_at=now - timedelta(hours=1), last_reviewed_at=now)
    )
