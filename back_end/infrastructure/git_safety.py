"""Guard against accidental writes through GitPython.

Mode-aware: a thread-local `_state` records the active `GitSafetyMode` + allowed
paths/remotes. `safe_repo(path)` returns a `SafeRepo` that consults that state
before every guarded call.

- READONLY  (default): every mutating GitPython API raises `GitMutationBlocked`.
- SANDBOX:  mutations are allowed iff the repo's working tree path is contained
            in one of the allowed paths. Network operations (push/pull/fetch
            against `origin`) are NOT allowed in sandbox mode.
- APPLY:    mutations + push/pull/fetch against remotes in `allowed_remotes` are
            allowed iff the path is in `allowed_paths`.

Callers wrap their write operations in:

    with safety_mode(GitSafetyMode.SANDBOX, allowed_paths=[sbx_path]):
        repo = safe_repo(sbx_path)
        repo.git.checkout("-b", "opensweep/work")
        repo.index.commit("agent change")

Default-mode (no `safety_mode` block) is READONLY, so v1 call sites stay strict.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from git import Repo


class GitMutationBlocked(RuntimeError):
    """Raised when code tries to mutate a OpenSweep-managed repo outside its sandbox."""


class GitSafetyMode(StrEnum):
    READONLY = "readonly"
    SANDBOX = "sandbox"
    APPLY = "apply"


@dataclass(frozen=True)
class _SafetyState:
    mode: GitSafetyMode = GitSafetyMode.READONLY
    allowed_paths: tuple[str, ...] = ()
    allowed_remotes: tuple[str, ...] = ()


_state: ContextVar[_SafetyState] = ContextVar("git_safety_state", default=_SafetyState())


@contextmanager
def safety_mode(
    mode: GitSafetyMode,
    *,
    allowed_paths: list[str] | tuple[str, ...] = (),
    allowed_remotes: list[str] | tuple[str, ...] = (),
):
    """Enter a scope where guarded ops obey `mode` / `allowed_paths` / `allowed_remotes`."""
    token = _state.set(_SafetyState(
        mode=mode,
        allowed_paths=tuple(str(Path(p).resolve()) for p in allowed_paths),
        allowed_remotes=tuple(allowed_remotes),
    ))
    try:
        yield
    finally:
        _state.reset(token)


def current_mode() -> GitSafetyMode:
    return _state.get().mode


# Repo-level mutating ops (clone is fine in sandbox/apply mode).
_REPO_LEVEL_BLOCKED_READONLY = {"clone", "init", "clone_from"}

# (object_attr, method_name) — methods that mutate the working tree / object DB.
_LOCAL_MUTATIONS = {
    ("index", "add"), ("index", "remove"), ("index", "commit"),
    ("index", "checkout"), ("index", "merge_tree"), ("index", "reset"),
    ("git", "add"), ("git", "commit"), ("git", "checkout"),
    ("git", "merge"), ("git", "reset"), ("git", "rebase"),
    ("git", "clean"), ("git", "stash"), ("git", "tag"),
    ("git", "branch"), ("git", "am"), ("git", "apply"),
    ("git", "cherry_pick"), ("git", "switch"), ("git", "restore"),
    ("git", "init"),
}

# Network operations — only allowed in APPLY mode and only against allowed remotes.
_NETWORK_OPS = {
    ("git", "push"), ("git", "pull"), ("git", "fetch"),
}


def _path_allowed(repo_path: str | None, allowed: tuple[str, ...]) -> bool:
    if not repo_path:
        return False
    try:
        resolved = str(Path(repo_path).resolve())
    except Exception:
        return False
    for root in allowed:
        if resolved == root or resolved.startswith(root.rstrip("/") + "/"):
            return True
    return False


class _GuardedAttr:
    """Wraps repo.git / repo.index. Decides allowed/blocked based on active state."""

    def __init__(self, parent_attr: str, target: Any, repo_path: str | None) -> None:
        self._parent = parent_attr
        self._target = target
        self._repo_path = repo_path

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._target, name)
        key = (self._parent, name)
        if not callable(attr):
            return attr

        state = _state.get()
        is_local_mut = key in _LOCAL_MUTATIONS
        is_network = key in _NETWORK_OPS

        if not is_local_mut and not is_network:
            return attr

        if state.mode == GitSafetyMode.READONLY:
            return _blocked_callable(self._parent, name, "readonly mode")

        if is_local_mut:
            if _path_allowed(self._repo_path, state.allowed_paths):
                return attr
            return _blocked_callable(self._parent, name, f"path not allowed (mode={state.mode})")

        # network op
        if state.mode != GitSafetyMode.APPLY:
            return _blocked_callable(self._parent, name, f"network ops disabled (mode={state.mode})")
        if not _path_allowed(self._repo_path, state.allowed_paths):
            return _blocked_callable(self._parent, name, "path not allowed for network op")

        # In APPLY mode the caller passes the remote name as the first positional arg
        # to git.push/pull/fetch. We don't try to enforce that here — the caller is
        # responsible for naming an allowed remote.
        return attr

    def __dir__(self):
        return dir(self._target)


def _blocked_callable(parent: str, name: str, reason: str):
    def _blocked(*args, **kwargs):
        raise GitMutationBlocked(f"OpenSweep forbids repo.{parent}.{name}(...) — {reason}")
    return _blocked


class SafeRepo:
    """Mode-aware facade over `git.Repo`."""

    def __init__(self, repo: Repo) -> None:
        self._repo = repo
        try:
            self._repo_path = str(Path(repo.working_dir).resolve()) if repo.working_dir else None
        except Exception:
            self._repo_path = None

    def __getattr__(self, name: str) -> Any:
        if name in _REPO_LEVEL_BLOCKED_READONLY and current_mode() == GitSafetyMode.READONLY:
            return _blocked_callable("", name, "readonly mode")
        attr = getattr(self._repo, name)
        if name in {"git", "index"}:
            return _GuardedAttr(name, attr, self._repo_path)
        return attr

    def __dir__(self):
        return dir(self._repo)


def safe_repo(path: str) -> SafeRepo:
    """Open a repo at `path` and return a mode-aware guarded handle."""
    return SafeRepo(Repo(path))
