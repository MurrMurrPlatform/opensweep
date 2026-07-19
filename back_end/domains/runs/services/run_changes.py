"""Per-run file changes (tree + unified diffs) for the run Files tab.

Computed live from the workspace git state and snapshotted to
{ARTIFACT_STORE_ROOT}/runs/{uid}.changes.json at turn boundaries so the view
survives workspace teardown. `GET /runs/{uid}/changes` prefers the live
compute while the workspace exists and falls back to the last snapshot.

Best-effort throughout: failures never break a run — snapshot_changes
swallows everything and read_changes degrades to snapshot/none. Read-only
local git; no tokens involved.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from config import settings
from domains.runs.services.workspace import live_workspace_path
from logging_config import logger

# Per-file unified patch budget; beyond it the patch is dropped (too_large).
PATCH_MAX_CHARS = 200_000
# Untracked files bigger than this are listed but never diffed.
UNTRACKED_MAX_BYTES = 400_000
# Overall serialized budget: the largest patches are dropped until it fits.
TOTAL_MAX_BYTES = 4_000_000

_STATUS_BY_LETTER = {
    "A": "added",
    "M": "modified",
    "D": "deleted",
    "T": "modified",
    "C": "added",
}

_EMPTY = {"source": "none", "base": "", "captured_at": None, "files": [], "tree": []}


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[:128]


def changes_path(run_uid: str) -> Path:
    root = getattr(settings, "ARTIFACT_STORE_ROOT", None) or "var/artifacts"
    return Path(root) / "runs" / f"{_safe(run_uid or 'unknown')}.changes.json"


async def _git(path: str, *args: str, ok_codes: tuple[int, ...] = (0,)) -> str:
    """Run git in the workspace, return stdout. Read-only local git — no
    credentials ever pass through here.

    core.quotepath=false keeps non-ASCII paths literal (quoted+octal paths
    would break the name↔patch matching); GIT_OPTIONAL_LOCKS=0 stops status/
    diff from taking .git/index.lock, so a Files-tab read can never fail the
    agent's own concurrent git commands."""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-c",
        "core.quotepath=false",
        "-C",
        path,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    out, err = await proc.communicate()
    if proc.returncode not in ok_codes:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {err.decode(errors='replace')[:300]}"
        )
    return out.decode(errors="replace")


def _new_entry(path: str, *, status: str, old_path: str = "") -> dict:
    return {
        "path": path,
        "old_path": old_path,
        "status": status,
        "additions": 0,
        "deletions": 0,
        "patch": "",
        "binary": False,
        "too_large": False,
    }


def _numstat_path(field: str) -> str:
    """New path from a numstat path field, resolving rename notation:
    `old => new` and the abbreviated `pre{old => new}post` form."""
    if " => " not in field:
        return field
    if "{" in field and "}" in field:
        pre, _, rest = field.partition("{")
        inner, _, post = rest.partition("}")
        new = inner.split(" => ")[-1]
        return (pre + new + post).replace("//", "/")
    return field.split(" => ")[-1]


def _strip_ab_prefix(p: str) -> str:
    return p[2:] if p.startswith(("a/", "b/")) else p


def _split_patch_segments(diff_text: str) -> dict[str, tuple[str, bool]]:
    """Split one whole `git diff` output into per-file segments.

    Returns {path: (patch_text, binary)}. The path is taken from the
    `+++ b/<path>` / `--- a/<path>` header pair (handling /dev/null), with
    the `diff --git a/x b/y` line as the fallback for binary/mode-only
    segments that carry no ---/+++ headers.
    """
    out: dict[str, tuple[str, bool]] = {}
    if not diff_text.strip():
        return out
    for chunk in ("\n" + diff_text).split("\ndiff --git ")[1:]:
        segment = "diff --git " + chunk
        binary = False
        old = new = ""
        for line in segment.splitlines():
            if line.startswith("@@"):
                break  # headers only live before the first hunk
            if line.startswith("Binary files "):
                binary = True
            elif line.startswith("--- ") and not old:
                old = line[4:].split("\t")[0].strip()
            elif line.startswith("+++ ") and not new:
                new = line[4:].split("\t")[0].strip()
        if new and new != "/dev/null":
            path = _strip_ab_prefix(new)
        elif old and old != "/dev/null":
            path = _strip_ab_prefix(old)
        else:
            header = segment.splitlines()[0]
            idx = header.rfind(" b/")
            path = header[idx + 3 :].strip() if idx != -1 else ""
        if path:
            out[path] = (segment, binary)
    return out


def _untracked_paths(porcelain_z: str) -> list[str]:
    """`??` paths from `git status --porcelain=v1 -z` output. Rename/copy
    entries carry a second NUL-separated path that must be skipped."""
    paths: list[str] = []
    tokens = porcelain_z.split("\0")
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if len(token) < 4:
            continue
        xy, path = token[:2], token[3:]
        if "R" in xy or "C" in xy:
            i += 1  # the origin path rides in the next token
        if xy == "??" and path:
            paths.append(path)
    return paths


def _spec_refs(spec: dict) -> tuple[str, str]:
    """(preferred, fallback) branch names for the diff base, by workspace
    purpose. Write workspaces diff against the recorded base branch so the
    Files tab shows the run's cumulative work even across workspace
    recreations; discovery workspaces diff against the cloned source branch
    so a chat on a PR shows only what the agent touched, not the whole PR."""
    base = str(spec.get("base_branch") or "")
    source = str(spec.get("source_branch") or spec.get("work_branch") or "")
    if str(spec.get("purpose") or "discovery") == "write":
        return base, source
    return source, base


async def _resolve_base(workspace_path: str, base_ref: str, source_ref: str) -> str:
    """First candidate that resolves wins — callers order base_ref/source_ref
    by workspace purpose (see _spec_refs)."""
    candidates = []
    if base_ref:
        candidates.append(f"origin/{base_ref}")
    if source_ref:
        candidates.append(f"origin/{source_ref}")
    candidates.append("HEAD")
    for ref in candidates:
        try:
            out = await _git(
                workspace_path,
                "rev-parse",
                "--verify",
                "--quiet",
                f"{ref}^{{commit}}",
                ok_codes=(0, 1),
            )
        except RuntimeError:
            continue
        if out.strip():
            return ref
    return "HEAD"


def _enforce_total_budget(result: dict, max_bytes: int = TOTAL_MAX_BYTES) -> None:
    """Drop the largest patches (marking too_large) until the payload fits
    the budget — single pass, sized without re-serializing the whole result
    per drop (a big run would otherwise cost seconds of blocking dumps)."""
    base_size = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    if base_size <= max_bytes:
        return
    with_patches = sorted(
        (f for f in result["files"] if f.get("patch")),
        key=lambda f: len(f["patch"]),
        reverse=True,
    )
    for f in with_patches:
        if base_size <= max_bytes:
            break
        base_size -= len(f["patch"].encode("utf-8"))
        f["patch"] = ""
        f["too_large"] = True


async def compute_changes(
    workspace_path: str, *, base_ref: str = "", source_ref: str = ""
) -> dict:
    """Changed files vs the resolved base ref INCLUDING uncommitted
    working-tree changes (two-dot diff base→working tree: covers the agent's
    commits AND uncommitted edits in a fresh clone), plus untracked files."""
    base = await _resolve_base(workspace_path, base_ref, source_ref)
    numstat_out = await _git(
        workspace_path, "diff", "--no-color", "--find-renames", "--numstat", base
    )
    name_status_out = await _git(
        workspace_path, "diff", "--no-color", "--find-renames", "--name-status", base
    )
    full_diff = await _git(workspace_path, "diff", "--no-color", "--find-renames", base)
    patches = _split_patch_segments(full_diff)

    files: dict[str, dict] = {}
    for line in name_status_out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0]:
            continue
        letter = parts[0].strip()
        if letter[:1] in {"R", "C"} and len(parts) >= 3:
            old, new = parts[1], parts[2]
            if letter[:1] == "R":
                entry = _new_entry(new, status="renamed", old_path=old)
            else:
                entry = _new_entry(new, status="added")
        else:
            entry = _new_entry(
                parts[-1], status=_STATUS_BY_LETTER.get(letter[:1], "modified")
            )
        files[entry["path"]] = entry

    for line in numstat_out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        add_s, del_s, path_field = parts
        path = _numstat_path(path_field)
        entry = files.setdefault(path, _new_entry(path, status="modified"))
        if add_s == "-" or del_s == "-":
            entry["binary"] = True  # numstat marks binary content with "-"
        else:
            try:
                entry["additions"] = int(add_s)
                entry["deletions"] = int(del_s)
            except ValueError:
                pass

    for path, (patch, binary) in patches.items():
        entry = files.get(path)
        if entry is None:
            continue
        if binary or entry["binary"]:
            entry["binary"] = True
            entry["patch"] = ""
        elif len(patch) > PATCH_MAX_CHARS:
            entry["too_large"] = True
            entry["patch"] = ""
        else:
            entry["patch"] = patch

    # Untracked files: not in any diff vs base, but they ARE the agent's work.
    status_out = await _git(
        workspace_path, "status", "--porcelain=v1", "-z", "--untracked-files=all"
    )
    for path in _untracked_paths(status_out):
        if path in files:
            continue
        entry = _new_entry(path, status="added")
        files[path] = entry
        fs_path = Path(workspace_path) / path
        try:
            size = fs_path.stat().st_size
        except OSError:
            size = 0
        if size > UNTRACKED_MAX_BYTES:
            entry["too_large"] = True
            continue
        try:
            with open(fs_path, "rb") as fh:
                head = fh.read(8192)
        except OSError:
            head = b""
        if b"\x00" in head:
            entry["binary"] = True
            continue
        # --no-index exits 1 when the files differ — that IS the success case.
        patch = await _git(
            workspace_path,
            "diff",
            "--no-color",
            "--no-index",
            "--",
            "/dev/null",
            path,
            ok_codes=(0, 1),
        )
        entry["additions"] = sum(
            1
            for line in patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        if len(patch) > PATCH_MAX_CHARS:
            entry["too_large"] = True
        else:
            entry["patch"] = patch

    ls_out = await _git(workspace_path, "ls-files")
    tree = {line for line in ls_out.splitlines() if line}
    tree.update(files.keys())

    result = {
        "source": "live",
        "base": base,
        "captured_at": datetime.now(UTC).isoformat(),
        "files": sorted(files.values(), key=lambda f: f["path"]),
        "tree": sorted(tree),
    }
    _enforce_total_budget(result)
    return result


async def snapshot_changes(run) -> None:
    """Snapshot the run's live changes to {uid}.changes.json. Silent on any
    failure — the Files tab is observability, never turn-fatal."""
    try:
        path = await live_workspace_path(run)
        if path is None:
            return
        preferred, fallback = _spec_refs(dict(run.workspace_spec or {}))
        data = await compute_changes(path, base_ref=preferred, source_ref=fallback)
        out = changes_path(run.uid)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 — best-effort, never break a run
        logger.warning(
            f"run {getattr(run, 'uid', '?')}: changes snapshot failed: {exc}",
            extra={"tag": "runs"},
        )


async def read_changes(run) -> dict:
    """Live compute while the workspace exists, else the last snapshot, else
    an empty payload with source='none'."""
    path = None
    try:
        path = await live_workspace_path(run)
    except Exception:  # noqa: BLE001
        path = None
    if path is not None:
        try:
            preferred, fallback = _spec_refs(dict(run.workspace_spec or {}))
            return await compute_changes(path, base_ref=preferred, source_ref=fallback)
        except Exception as exc:  # noqa: BLE001 — degrade to the snapshot
            logger.warning(
                f"run {getattr(run, 'uid', '?')}: live changes compute failed: {exc}",
                extra={"tag": "runs"},
            )
    try:
        data = json.loads(changes_path(run.uid).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data["source"] = "snapshot"
            return data
    except (OSError, ValueError):
        pass
    return dict(_EMPTY)
