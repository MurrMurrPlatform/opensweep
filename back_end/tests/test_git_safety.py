"""Verify git_safety wraps git.Repo and blocks mutations on a real on-disk repo."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from infrastructure.git_safety import GitMutationBlocked, safe_repo


@pytest.fixture
def tmp_repo() -> str:
    d = tempfile.mkdtemp(prefix="opensweep-gitsafety-")
    subprocess.run(["git", "init", "-q", d], check=True)
    subprocess.run(["git", "-C", d, "config", "user.email", "x@x.x"], check=True)
    subprocess.run(["git", "-C", d, "config", "user.name", "x"], check=True)
    (Path(d) / "README.md").write_text("hello")
    subprocess.run(["git", "-C", d, "add", "README.md"], check=True)
    subprocess.run(["git", "-C", d, "commit", "-q", "-m", "init"], check=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_read_operations_work(tmp_repo):
    r = safe_repo(tmp_repo)
    # Read-only access is fine
    assert r.active_branch is not None
    assert len(list(r.iter_commits())) == 1


def test_index_add_blocked(tmp_repo):
    r = safe_repo(tmp_repo)
    (Path(tmp_repo) / "new.txt").write_text("x")
    with pytest.raises(GitMutationBlocked):
        r.index.add(["new.txt"])


def test_git_commit_blocked(tmp_repo):
    r = safe_repo(tmp_repo)
    with pytest.raises(GitMutationBlocked):
        r.git.commit("-m", "bad")


def test_git_checkout_blocked(tmp_repo):
    r = safe_repo(tmp_repo)
    with pytest.raises(GitMutationBlocked):
        r.git.checkout("HEAD")
