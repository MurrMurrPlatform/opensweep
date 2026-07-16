"""Pure-Python tests for the docs-to-repo export rendering (Proposal 3).

The git/PR flow is integration-tested; here we pin the pure rendering:
marker preservation in AGENTS.md, slug→file mapping, and the
managed-file guard that keeps the mirror from deleting human files.
"""

from types import SimpleNamespace

from domains.docs.services.repo_export import (
    doc_file_path,
    is_opensweep_managed,
    merge_agents_md,
    render_agents_block,
    render_doc_file,
)


def _doc(slug, title="", summary="", body="content", pinned=False, watch_paths=None):
    return SimpleNamespace(
        slug=slug,
        title=title,
        summary=summary,
        body=body,
        pinned=pinned,
        watch_paths=watch_paths or [],
    )


def test_doc_file_path_maps_folders():
    assert doc_file_path("conventions") == "docs/conventions.md"
    assert doc_file_path("backend/queue-workers") == "docs/backend/queue-workers.md"


def test_rendered_doc_files_are_marked_managed():
    text = render_doc_file(_doc("backend/api", title="API", watch_paths=["back_end/api"]))
    assert is_opensweep_managed(text)
    assert "# API" in text
    assert "back_end/api" in text


def test_unmarked_files_are_never_managed():
    assert not is_opensweep_managed("# My handwritten doc\n")
    assert not is_opensweep_managed("")


def test_agents_block_inlines_pinned_and_indexes_all():
    docs = [
        _doc("conventions", title="Conventions", body="Use tabs.", pinned=True),
        _doc("backend/api", title="API", summary="the http surface"),
    ]
    block = render_agents_block(docs)
    assert "Use tabs." in block  # pinned body verbatim
    assert "docs/backend/api.md" in block  # indexed
    assert "the http surface" in block


def test_merge_preserves_user_content_outside_markers():
    docs = [_doc("conventions", body="v1", pinned=True)]
    block = render_agents_block(docs)
    existing = "# My own intro\n\n" + block + "\n\n# My own footer\n"
    updated = merge_agents_md(
        existing, render_agents_block([_doc("conventions", body="v2", pinned=True)])
    )
    assert "# My own intro" in updated
    assert "# My own footer" in updated
    assert "v2" in updated
    assert "v1" not in updated


def test_merge_appends_block_to_agents_md_without_markers():
    updated = merge_agents_md("# Existing hand-written AGENTS.md\n", "<!-- OPENSWEEP:START — managed by OpenSweep; edits inside this block are overwritten on sync -->\nblock\n<!-- OPENSWEEP:END -->\n")
    assert updated.startswith("# Existing hand-written AGENTS.md")
    assert "block" in updated
