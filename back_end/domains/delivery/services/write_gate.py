"""Write-path git safety gate (PLATFORM_V2_DESIGN.md §6, §15 Phase 3).

Agents edit files and commit INSIDE the sandbox; this module is the
deterministic platform code that validates the sandbox git state and performs
the push. The GitHub credential (App installation token or PAT — callers
resolve it via `infrastructure.git_providers.get_git_credentials` and pass it in)
never enters the agent process — it travels only in a per-invocation
`git -c http.extraHeader=…` here (same technique as the sandbox clone), and
error output is redacted for whichever token was used.

Everything decision-shaped is a pure function (`denylist_violations`,
`is_protected_branch`, `evaluate_changes`, `fix_rounds_exhausted`) so the
safety rules are unit-testable without git. `validate_sandbox_changes` and
`push_work_branch` are the only pieces that shell out.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

from config import settings
from infrastructure.git_auth import git_auth_extraheader
from domains.delivery.models import DEFAULT_PATH_DENYLIST
from logging_config import logger

# Branch names that platform code will never push to, regardless of policy.
PROTECTED_BRANCH_NAMES = frozenset({"main", "master", "develop"})


@dataclass
class WriteGateResult:
    ok: bool
    changed_paths: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    commits: int = 0

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "changed_paths": list(self.changed_paths),
            "violations": list(self.violations),
            "commits": self.commits,
        }


def effective_denylist(policy) -> list[str]:
    """Path denylist for a MergePolicy node/DTO-ish object.

    `None` (pre-Phase-3 nodes without the property) falls back to the
    defaults; an explicit empty list is an operator opt-out and is honoured.
    """
    raw = getattr(policy, "path_denylist", None)
    if raw is None:
        return list(DEFAULT_PATH_DENYLIST)
    return [str(p) for p in raw]


def denylist_violations(changed_paths: list[str], patterns: list[str]) -> list[str]:
    """Changed paths that match any denylist regex → violation strings.

    Fails closed: an invalid regex is itself a violation (a broken policy
    must never silently allow a push).
    """
    violations: list[str] = []
    compiled: list[tuple[str, re.Pattern]] = []
    for pattern in patterns:
        try:
            compiled.append((pattern, re.compile(pattern)))
        except re.error as exc:
            violations.append(f"invalid denylist pattern {pattern!r}: {exc}")
    for path in changed_paths:
        for pattern, rx in compiled:
            if rx.search(path):
                violations.append(f"path {path!r} matches denylisted pattern {pattern!r}")
                break
    return violations


def is_protected_branch(branch: str, *, default_branch: str = "main") -> bool:
    name = (branch or "").strip()
    if not name:
        return True  # detached HEAD / unknown — never push blind
    return name == (default_branch or "main").strip() or name in PROTECTED_BRANCH_NAMES


def fix_rounds_exhausted(fix_rounds: int, max_fix_rounds: int) -> bool:
    """The bounded auto-fix loop (§6): counter lives on the PullRequest."""
    return int(fix_rounds or 0) >= int(max_fix_rounds or 0)


NO_COMMITS_VIOLATION = "no commits on the work branch — nothing to push"


def is_only_no_commits(violations: list[str]) -> bool:
    """A turn that simply produced no commits (conversation, planning, Q&A)
    — not a real gate violation. Thread runs finalize every turn, so their
    chatty turns must stay quiet instead of auditing as blocked."""
    return violations == [NO_COMMITS_VIOLATION]


def evaluate_changes(
    *,
    work_branch: str,
    changed_paths: list[str],
    commits: int,
    denylist: list[str],
    default_branch: str = "main",
) -> WriteGateResult:
    """Pure decision core — everything the gate checks, no git required."""
    violations: list[str] = []
    if is_protected_branch(work_branch, default_branch=default_branch):
        violations.append(
            f"work branch {work_branch!r} is a protected branch — writes go to opensweep/* branches only"
        )
    if commits <= 0:
        violations.append(NO_COMMITS_VIOLATION)
    violations.extend(denylist_violations(changed_paths, denylist))
    return WriteGateResult(
        ok=not violations,
        changed_paths=list(changed_paths),
        violations=violations,
        commits=commits,
    )


async def validate_sandbox_changes(
    sandbox_path: str,
    *,
    base_ref: str,
    policy,
    default_branch: str = "main",
) -> WriteGateResult:
    """Inspect the sandbox git state and run the gate.

    Platform code inspecting `git` output — never prompt instructions. The
    diff/commit window is `origin/{base_ref}..HEAD`: for implement-runs
    base_ref is the repo base branch; for fix-runs it is the PR head branch
    as it existed on the remote, so only the agent's new work is judged.
    """
    try:
        work_branch = (
            await _git(sandbox_path, "rev-parse", "--abbrev-ref", "HEAD")
        ).strip()
        diff_out = await _git(
            sandbox_path, "diff", "--name-only", f"origin/{base_ref}...HEAD"
        )
        commits_out = await _git(
            sandbox_path, "rev-list", "--count", f"origin/{base_ref}..HEAD"
        )
    except RuntimeError as exc:
        return WriteGateResult(ok=False, violations=[f"git inspection failed: {exc}"])

    changed_paths = [line.strip() for line in diff_out.splitlines() if line.strip()]
    try:
        commits = int(commits_out.strip() or "0")
    except ValueError:
        commits = 0
    return evaluate_changes(
        work_branch=work_branch,
        changed_paths=changed_paths,
        commits=commits,
        denylist=effective_denylist(policy),
        default_branch=default_branch,
    )


async def push_work_branch(
    sandbox_path: str, *, work_branch: str, token: str, default_branch: str = "main"
) -> None:
    """Push the validated work branch. Platform-only; NEVER --force.

    `token` is the resolved GitHub credential for THIS repo (installation
    token when the App covers it, else the PAT — callers use
    `infrastructure.git_providers.get_git_credentials`). Auth uses the same
    transient extraHeader as the clone so the token is never persisted in
    the sandbox and never visible to the agent.
    """
    if is_protected_branch(work_branch, default_branch=default_branch):
        raise RuntimeError(
            f"refusing to push protected branch {work_branch!r} (default={default_branch!r})"
        )
    if not token:
        raise RuntimeError(
            "cannot push: no GitHub credential (connect the GitHub App or set GITHUB_TOKEN)"
        )
    await _git(
        sandbox_path,
        "-c",
        git_auth_extraheader(token),
        "push",
        "origin",
        work_branch,
        redact_token=token,
    )
    logger.info(
        f"write_gate: pushed {work_branch} from {sandbox_path}", extra={"tag": "write_gate"}
    )


async def _git(sandbox_path: str, *args: str, redact_token: str = "") -> str:
    """Run git in the sandbox, return stdout. Errors are token-redacted for
    whichever credential was used (PAT and/or installation token)."""
    cmd = ["git", "-C", sandbox_path, *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        message = (
            f"git {' '.join(a for a in args if not a.startswith('http.extraHeader'))} "
            f"failed: {err.decode(errors='replace')[:300]}"
        )
        for secret in (redact_token, settings.GITHUB_TOKEN):
            if secret:
                message = message.replace(secret, "***")
        raise RuntimeError(message)
    return out.decode(errors="replace")
