"""Import audit-relevant agent prompts from github.com/affaan-m/ECC.

ECC ships 79 commands + 63 agents. We import a curated subset (the
audit-relevant ones) and map their YAML frontmatter + markdown body into
Agent rows.

User-edited prompts (provenance='user') are sticky — re-import skips them so
your edits aren't clobbered.

Source is MIT-licensed; attribution is preserved via `source_url` +
`source_commit`.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess  # CalledProcessError only — processes run via asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from domains.agents.models import Agent
from domains.agents.schemas import ImportEccResult
from logging_config import logger

# Allowed audit-relevant files. Pulled from inspection of the ECC repo;
# see plan §Phase C.
ECC_AUDIT_COMMANDS: list[str] = [
    "code-review.md",
    "review-pr.md",
    "security-scan.md",
    "harness-audit.md",
    "test-coverage.md",
    "quality-gate.md",
    "refactor-clean.md",
    "python-review.md",
    "go-review.md",
    "rust-review.md",
    "react-review.md",
    "kotlin-review.md",
    "fastapi-review.md",
    "cpp-review.md",
    "flutter-review.md",
]

# Reviewer / auditor agents — the codified "specialists" we expose as prompts.
ECC_AUDIT_AGENTS: list[str] = [
    "code-reviewer.md",
    "code-architect.md",
    "code-simplifier.md",
    "code-explorer.md",
    "comment-analyzer.md",
    "database-reviewer.md",
    "doc-updater.md",
    "fastapi-reviewer.md",
    "go-reviewer.md",
    "django-reviewer.md",
    "flutter-reviewer.md",
    "csharp-reviewer.md",
    "fsharp-reviewer.md",
]

ECC_REPO_URL = "https://github.com/affaan-m/ECC.git"
# In-container the backend lives at /app; outside it (migration tool, local
# dev) fall back to the repo-relative back_end/var/ecc-source.
ECC_CLONE_DIR = (
    Path("/app/var/ecc-source")
    if Path("/app").is_dir()
    else Path(__file__).resolve().parents[3] / "var" / "ecc-source"
)
ECC_RAW_BASE = "https://raw.githubusercontent.com/affaan-m/ECC"


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def _parse_markdown(text: str) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter from markdown body. Returns (metadata, body)."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return meta if isinstance(meta, dict) else {}, m.group(2)


def _extract_title(body: str, fallback: str) -> str:
    m = _H1_RE.search(body)
    if m:
        return m.group(1).strip()
    return fallback


def _infer_tags(slug: str, meta: dict[str, Any]) -> list[str]:
    """Map ECC filename slug → free-text OpenSweep tags (no taxonomy)."""
    name = slug.replace(".md", "").lower()
    tags: list[str] = []

    if "security" in name:
        tags = ["security"]
    elif "test" in name:
        tags = ["tests"]
    elif "quality-gate" in name:
        tags = ["quality", "correctness", "conventions", "maintainability"]
    elif "refactor" in name or "simplifier" in name:
        tags = ["refactor", "maintainability"]
    elif "harness-audit" in name:
        tags = ["harness", "maintainability", "ops"]
    elif "doc" in name or "comment-analyzer" in name:
        tags = ["docs"]
    elif "architect" in name or "explorer" in name:
        tags = ["architecture", "maintainability"]
    elif name.startswith("review-pr") or "code-review" in name or name == "code-reviewer":
        tags = ["code-review", "correctness", "maintainability"]
    else:
        # Language-specific reviewers: e.g. python-review, go-review, fastapi-review.
        tags = ["code-review", "correctness", "conventions", "maintainability"]
        for lang in (
            "python",
            "go",
            "rust",
            "react",
            "kotlin",
            "fastapi",
            "cpp",
            "flutter",
            "csharp",
            "fsharp",
            "django",
            "database",
        ):
            if lang in name:
                tags.append(f"language:{lang}")
                break

    if isinstance(meta.get("description"), str):
        # description from frontmatter often contains keywords — not great as tag, skip
        pass
    if isinstance(meta.get("tools"), list):
        tags.append("agent")

    return sorted(set(tags))


async def _run_git(args: list[str], *, cwd: Path | None = None) -> bytes:
    """Run git without blocking the event loop; raises CalledProcessError on
    failure (stderr attached) so callers keep subprocess.run error handling."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd) if cwd is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode or 1, args, output=stdout, stderr=stderr
        )
    return stdout


async def _clone_or_pull() -> str:
    """Clone the ECC repo (or fast-forward pull if already cloned).

    Returns the resolved commit SHA.
    """
    if ECC_CLONE_DIR.exists() and (ECC_CLONE_DIR / ".git").exists():
        await _run_git(["git", "fetch", "--depth=1", "origin"], cwd=ECC_CLONE_DIR)
        await _run_git(["git", "reset", "--hard", "origin/HEAD"], cwd=ECC_CLONE_DIR)
    else:
        ECC_CLONE_DIR.parent.mkdir(parents=True, exist_ok=True)
        if ECC_CLONE_DIR.exists():
            shutil.rmtree(ECC_CLONE_DIR)
        await _run_git(["git", "clone", "--depth=1", ECC_REPO_URL, str(ECC_CLONE_DIR)])
    stdout = await _run_git(["git", "rev-parse", "HEAD"], cwd=ECC_CLONE_DIR)
    return stdout.decode().strip()


def _file_url(commit: str, kind: str, filename: str) -> str:
    return f"{ECC_RAW_BASE}/{commit}/{kind}/{filename}"


async def import_ecc(*, force: bool = False) -> ImportEccResult:
    """Clone ECC and upsert audit-relevant prompts as Agent rows.

    `force=False` keeps existing user-edited prompts intact and only updates
    rows whose `provenance='imported'` and content has changed.
    """
    errors: list[str] = []
    try:
        commit = await _clone_or_pull()
    except subprocess.CalledProcessError as exc:
        msg = f"git clone/pull failed: {exc.stderr.decode(errors='replace')[:300]}"
        logger.error(msg)
        return ImportEccResult(
            imported=0, skipped_user_edited=0, source_commit="", errors=[msg]
        )

    existing_rows = await Agent.nodes.all()
    by_url: dict[str, Agent] = {}
    for p in existing_rows:
        if p.source_url:
            by_url[p.source_url] = p

    imported = 0
    skipped = 0

    for kind, filenames in (
        ("commands", ECC_AUDIT_COMMANDS),
        ("agents", ECC_AUDIT_AGENTS),
    ):
        for filename in filenames:
            path = ECC_CLONE_DIR / kind / filename
            if not path.exists():
                errors.append(f"missing: {kind}/{filename}")
                continue
            try:
                text = path.read_text("utf-8", errors="replace")
                meta, body = _parse_markdown(text)
                slug = filename.replace(".md", "")
                title = _extract_title(body, slug.replace("-", " ").title())
                description = str(meta.get("description") or "")
                tags = _infer_tags(filename, meta)
                source_url = _file_url(commit, kind, filename)

                existing = by_url.get(source_url)
                if existing and existing.provenance == "user":
                    skipped += 1
                    continue

                now = datetime.now(timezone.utc)
                if existing is None:
                    p = Agent(
                        uid=uuid4().hex,
                        title=title,
                        description=description,
                        prompt=body.strip(),
                        produces="findings",
                        
                        default_effort="normal",
                        tags=tags,
                        provenance="imported",
                        source_url=source_url,
                        source_commit=commit,
                        enabled=True,
                    )
                    await p.save()
                    imported += 1
                else:
                    existing.title = title
                    existing.description = description
                    existing.prompt = body.strip()
                    existing.tags = tags
                    existing.source_commit = commit
                    existing.updated_at = now
                    await existing.save()
                    imported += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{kind}/{filename}: {type(exc).__name__}: {exc}")

    return ImportEccResult(
        imported=imported,
        skipped_user_edited=skipped,
        source_commit=commit,
        errors=errors,
    )
