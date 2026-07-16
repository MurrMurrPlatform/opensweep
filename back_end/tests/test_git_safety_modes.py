"""Mode-aware git_safety unit tests — no Neo4j needed."""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from infrastructure.git_safety import (
    GitMutationBlocked,
    GitSafetyMode,
    safe_repo,
    safety_mode,
)


@pytest.fixture
def tmp_repo() -> str:
    d = tempfile.mkdtemp(prefix="opensweep-git-modes-")
    subprocess.run(["git", "init", "-q", d], check=True)
    subprocess.run(["git", "-C", d, "config", "user.email", "x@x.x"], check=True)
    subprocess.run(["git", "-C", d, "config", "user.name", "x"], check=True)
    (Path(d) / "README.md").write_text("hello")
    subprocess.run(["git", "-C", d, "add", "README.md"], check=True)
    subprocess.run(["git", "-C", d, "commit", "-q", "-m", "init"], check=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_readonly_default_blocks_mutations(tmp_repo):
    r = safe_repo(tmp_repo)
    with pytest.raises(GitMutationBlocked):
        r.git.commit("-m", "x")


def test_sandbox_mode_allows_mutations_in_path(tmp_repo):
    r = safe_repo(tmp_repo)
    # Writing a file directly, then using a sandbox-allowed git commit
    (Path(tmp_repo) / "new.txt").write_text("data")
    with safety_mode(GitSafetyMode.SANDBOX, allowed_paths=[tmp_repo]):
        r2 = safe_repo(tmp_repo)
        r2.index.add(["new.txt"])
        r2.index.commit("sandbox commit")
    # Outside the context, mutations are blocked again.
    with pytest.raises(GitMutationBlocked):
        r.index.commit("nope")


def test_sandbox_mode_blocks_outside_path(tmp_repo):
    other = tempfile.mkdtemp(prefix="opensweep-git-other-")
    subprocess.run(["git", "init", "-q", other], check=True)
    subprocess.run(["git", "-C", other, "config", "user.email", "x@x.x"], check=True)
    subprocess.run(["git", "-C", other, "config", "user.name", "x"], check=True)
    try:
        r = safe_repo(other)
        with safety_mode(GitSafetyMode.SANDBOX, allowed_paths=[tmp_repo]):
            with pytest.raises(GitMutationBlocked):
                r.git.commit("--allow-empty", "-m", "should be blocked")
    finally:
        shutil.rmtree(other, ignore_errors=True)


def test_sandbox_mode_blocks_network_ops(tmp_repo):
    r = safe_repo(tmp_repo)
    with safety_mode(GitSafetyMode.SANDBOX, allowed_paths=[tmp_repo]):
        with pytest.raises(GitMutationBlocked):
            r.git.push("origin", "main")


def test_apply_mode_allows_push(tmp_repo):
    r = safe_repo(tmp_repo)
    with safety_mode(GitSafetyMode.APPLY, allowed_paths=[tmp_repo], allowed_remotes=["origin"]):
        # The git binary will fail (no origin remote) but the safety layer doesn't
        # raise GitMutationBlocked — confirming the call is allowed through.
        try:
            r.git.push("origin", "main")
        except GitMutationBlocked:
            pytest.fail("apply mode should not block push to allowed remote")
        except Exception:
            pass  # any other git error is fine
