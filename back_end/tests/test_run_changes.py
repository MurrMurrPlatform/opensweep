"""Per-run file changes (tree + diffs) — compute, snapshot, read fallbacks.

Real tmp git repos, no Neo4j: snapshot/read paths use a SimpleNamespace run
and monkeypatch `run_changes.live_workspace_path`.
"""

import json
import subprocess
import types
from pathlib import Path

import pytest

from config import settings
from domains.runs.services import run_changes
from domains.runs.services.run_changes import (
    changes_path,
    compute_changes,
    read_changes,
    snapshot_changes,
)


def _run(*args: str) -> str:
    return subprocess.run(
        args, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def tmp_repo(tmp_path) -> str:
    d = tmp_path / "ws"
    d.mkdir()
    p = str(d)
    _run("git", "init", "-q", p)
    _run("git", "-C", p, "config", "user.email", "x@x.x")
    _run("git", "-C", p, "config", "user.name", "x")
    (d / "a.txt").write_text("one\ntwo\nthree\n")
    (d / "gone.txt").write_text("bye\n")
    _run("git", "-C", p, "add", ".")
    _run("git", "-C", p, "commit", "-q", "-m", "base")
    return p


# ── compute_changes ──────────────────────────────────────────────────────────


async def test_working_tree_changes_added_modified_deleted(tmp_repo):
    d = Path(tmp_repo)
    (d / "a.txt").write_text("one\nTWO\nthree\nfour\n")  # modified
    (d / "new.txt").write_text("hello\nworld\n")  # untracked
    (d / "gone.txt").unlink()  # deleted

    result = await compute_changes(tmp_repo)

    assert result["source"] == "live"
    assert result["base"] == "HEAD"
    assert result["captured_at"]
    by_path = {f["path"]: f for f in result["files"]}
    assert by_path["a.txt"]["status"] == "modified"
    assert by_path["new.txt"]["status"] == "added"
    assert by_path["gone.txt"]["status"] == "deleted"

    # numstat sanity: one line replaced + one appended in a.txt.
    assert by_path["a.txt"]["additions"] == 2
    assert by_path["a.txt"]["deletions"] == 1
    assert by_path["new.txt"]["additions"] == 2
    assert by_path["gone.txt"]["deletions"] == 1

    assert "+TWO" in by_path["a.txt"]["patch"]
    assert "-two" in by_path["a.txt"]["patch"]
    assert "+hello" in by_path["new.txt"]["patch"]
    assert "-bye" in by_path["gone.txt"]["patch"]
    for f in result["files"]:
        assert not f["binary"] and not f["too_large"]

    # Tree: tracked paths plus the untracked file; sorted.
    assert "a.txt" in result["tree"]
    assert "gone.txt" in result["tree"]  # still tracked until committed
    assert "new.txt" in result["tree"]
    assert result["tree"] == sorted(result["tree"])
    # Files sorted by path.
    assert [f["path"] for f in result["files"]] == sorted(by_path)


async def test_committed_changes_vs_origin_base(tmp_repo):
    p = tmp_repo
    base_sha = _run("git", "-C", p, "rev-parse", "HEAD").strip()
    # Simulate a remote base without a network: a plain origin/ ref.
    _run("git", "-C", p, "update-ref", "refs/remotes/origin/main", base_sha)
    _run("git", "-C", p, "checkout", "-q", "-b", "work")
    (Path(p) / "a.txt").write_text("one\ntwo\nthree\ncommitted\n")
    _run("git", "-C", p, "commit", "-q", "-am", "work")

    result = await compute_changes(p, base_ref="main")

    assert result["base"] == "origin/main"
    by_path = {f["path"]: f for f in result["files"]}
    assert by_path["a.txt"]["status"] == "modified"
    assert by_path["a.txt"]["additions"] == 1
    assert "+committed" in by_path["a.txt"]["patch"]


async def test_missing_base_ref_falls_back_to_head(tmp_repo):
    result = await compute_changes(tmp_repo, base_ref="does-not-exist")
    assert result["base"] == "HEAD"


async def test_binary_untracked_file(tmp_repo):
    (Path(tmp_repo) / "blob.bin").write_bytes(b"\x00\x01\x02binary")
    result = await compute_changes(tmp_repo)
    by_path = {f["path"]: f for f in result["files"]}
    entry = by_path["blob.bin"]
    assert entry["status"] == "added"
    assert entry["binary"] is True
    assert entry["patch"] == ""


async def test_binary_tracked_change(tmp_repo):
    p = tmp_repo
    (Path(p) / "img.bin").write_bytes(b"\x00\x01")
    _run("git", "-C", p, "add", "img.bin")
    _run("git", "-C", p, "commit", "-q", "-m", "bin")
    (Path(p) / "img.bin").write_bytes(b"\x00\x02\x03")
    result = await compute_changes(p)
    entry = {f["path"]: f for f in result["files"]}["img.bin"]
    assert entry["binary"] is True
    assert entry["patch"] == ""
    assert entry["additions"] == 0 and entry["deletions"] == 0


async def test_oversized_untracked_file_is_too_large(tmp_repo):
    (Path(tmp_repo) / "big.txt").write_text("x" * 500_000)
    result = await compute_changes(tmp_repo)
    entry = {f["path"]: f for f in result["files"]}["big.txt"]
    assert entry["too_large"] is True
    assert entry["patch"] == ""


async def test_rename_detection(tmp_repo):
    p = tmp_repo
    base_sha = _run("git", "-C", p, "rev-parse", "HEAD").strip()
    _run("git", "-C", p, "update-ref", "refs/remotes/origin/main", base_sha)
    _run("git", "-C", p, "mv", "a.txt", "b.txt")
    _run("git", "-C", p, "commit", "-q", "-m", "rename")
    result = await compute_changes(p, base_ref="main")
    by_path = {f["path"]: f for f in result["files"]}
    assert by_path["b.txt"]["status"] == "renamed"
    assert by_path["b.txt"]["old_path"] == "a.txt"


# ── snapshot / read fallbacks ────────────────────────────────────────────────


def _fake_run(uid="run1"):
    return types.SimpleNamespace(
        uid=uid, workspace_spec={}, sandbox_uid="sb1"
    )


async def test_snapshot_roundtrip_and_snapshot_fallback(tmp_repo, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(tmp_path / "artifacts"))
    (Path(tmp_repo) / "new.txt").write_text("snap\n")
    run = _fake_run()

    async def _live(_run):
        return tmp_repo

    monkeypatch.setattr(run_changes, "live_workspace_path", _live)
    await snapshot_changes(run)
    assert changes_path(run.uid).exists()
    stored = json.loads(changes_path(run.uid).read_text(encoding="utf-8"))
    assert {f["path"] for f in stored["files"]} == {"new.txt"}

    # Live workspace present → fresh compute wins.
    live = await read_changes(run)
    assert live["source"] == "live"

    # Workspace gone → the snapshot serves the Files tab.
    async def _gone(_run):
        return None

    monkeypatch.setattr(run_changes, "live_workspace_path", _gone)
    snap = await read_changes(run)
    assert snap["source"] == "snapshot"
    assert {f["path"] for f in snap["files"]} == {"new.txt"}
    assert "+snap" in snap["files"][0]["patch"]


async def test_read_changes_without_workspace_or_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(tmp_path / "artifacts"))

    async def _gone(_run):
        return None

    monkeypatch.setattr(run_changes, "live_workspace_path", _gone)
    result = await read_changes(_fake_run("never-ran"))
    assert result == {
        "source": "none",
        "base": "",
        "captured_at": None,
        "files": [],
        "tree": [],
    }


async def test_snapshot_failure_is_silent(tmp_path, monkeypatch):
    # Artifact root pointing at a FILE → the write fails; must not raise.
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(blocker))

    async def _live(_run):
        return str(tmp_path / "not-a-repo")  # compute will fail too

    monkeypatch.setattr(run_changes, "live_workspace_path", _live)
    await snapshot_changes(_fake_run())  # must not raise


def test_changes_path_is_sanitized_and_under_runs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(tmp_path))
    p = changes_path("../../etc/passwd")
    assert p.parent == tmp_path / "runs"
    assert "/" not in p.name
    assert p.name.endswith(".changes.json")


def test_total_budget_drops_largest_patches():
    result = {
        "source": "live",
        "base": "HEAD",
        "captured_at": "t",
        "files": [
            {"path": "small.txt", "old_path": "", "status": "modified",
             "additions": 1, "deletions": 0, "patch": "+x", "binary": False,
             "too_large": False},
            {"path": "huge.txt", "old_path": "", "status": "modified",
             "additions": 1, "deletions": 0, "patch": "y" * 5000, "binary": False,
             "too_large": False},
        ],
        "tree": ["huge.txt", "small.txt"],
    }
    run_changes._enforce_total_budget(result, max_bytes=1000)
    by_path = {f["path"]: f for f in result["files"]}
    assert by_path["huge.txt"]["patch"] == ""
    assert by_path["huge.txt"]["too_large"] is True
    assert by_path["small.txt"]["patch"] == "+x"


def test_changes_route_is_mounted():
    from app import app

    schema = app.openapi()
    assert "/api/v1/runs/{uid}/changes" in schema["paths"]
    ops = {
        op.get("operationId")
        for methods in schema["paths"].values()
        for op in methods.values()
        if isinstance(op, dict)
    }
    assert "opensweep_run_changes" in ops
