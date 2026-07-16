"""Deterministic static-analysis candidates for review/ask runs (§E).

"Tools find candidates, the agent investigates": configured analyzers run
over the sandbox clone BEFORE the agent is dispatched; their raw output goes
to the artifact store and a capped, normalized candidate list is appended to
the run's context. A candidate is never a Finding — the agent confirms or
silently drops each one.

Always optional, mirroring infrastructure/code_graph.py: a missing binary,
a crash, or a timeout skips that tool with a note and never fails the run.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from config import settings
from logging_config import logger

ANALYZER_TOOLS = ("ruff", "vulture", "deptry", "semgrep", "knip")

ANALYZER_MODES = ("auto", "custom", "off")

_SEVERITIES = ("high", "medium", "low")


@dataclass(frozen=True)
class Candidate:
    tool: str
    rule: str
    path: str
    line: int
    message: str
    severity: str = "medium"


@dataclass
class AnalyzerReport:
    candidates: list[Candidate] = field(default_factory=list)
    tools_run: list[str] = field(default_factory=list)
    tools_skipped: list[dict] = field(default_factory=list)  # {tool, reason}
    raw_outputs: dict[str, str] = field(default_factory=dict)  # tool → raw stdout/stderr


# ── Parsers (pure) ───────────────────────────────────────────────────────────


def _parse_ruff(raw: str) -> list[Candidate]:
    """`ruff check --output-format json .` — F-rules (pyflakes: undefined
    names, unused imports…) are high; the rest medium."""
    try:
        items = json.loads(raw or "[]")
    except ValueError:
        return []
    out = []
    for it in items if isinstance(items, list) else []:
        code = str(it.get("code") or "")
        out.append(
            Candidate(
                tool="ruff",
                rule=code,
                path=str(it.get("filename") or ""),
                line=int((it.get("location") or {}).get("row") or 0),
                message=str(it.get("message") or ""),
                severity="high" if code.startswith("F8") else "medium",
            )
        )
    return out


def _parse_vulture(raw: str) -> list[Candidate]:
    """Text lines: `path:line: message (NN% confidence)` — dead code is a
    low-severity candidate (reachability needs the agent)."""
    out = []
    for line in (raw or "").splitlines():
        parts = line.split(":", 2)
        if len(parts) < 3 or not parts[1].strip().isdigit():
            continue
        out.append(
            Candidate(
                tool="vulture",
                rule="dead-code",
                path=parts[0].strip(),
                line=int(parts[1].strip()),
                message=parts[2].strip(),
                severity="low",
            )
        )
    return out


def _parse_deptry(raw: str) -> list[Candidate]:
    """deptry --json-output: [{error: {code, message}, module, location}]."""
    try:
        items = json.loads(raw or "[]")
    except ValueError:
        return []
    out = []
    for it in items if isinstance(items, list) else []:
        error = it.get("error") or {}
        location = it.get("location") or {}
        out.append(
            Candidate(
                tool="deptry",
                rule=str(error.get("code") or "dependency"),
                path=str(location.get("file") or "pyproject.toml"),
                line=int(location.get("line") or 0),
                message=str(error.get("message") or ""),
                severity="medium",
            )
        )
    return out


_SEMGREP_SEVERITY = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}


def _parse_semgrep(raw: str) -> list[Candidate]:
    """semgrep --json: {results: [{check_id, path, start.line, extra}]}."""
    try:
        payload = json.loads(raw or "{}")
    except ValueError:
        return []
    out = []
    for it in payload.get("results") or []:
        extra = it.get("extra") or {}
        out.append(
            Candidate(
                tool="semgrep",
                rule=str(it.get("check_id") or ""),
                path=str(it.get("path") or ""),
                line=int((it.get("start") or {}).get("line") or 0),
                message=str(extra.get("message") or "").strip(),
                severity=_SEMGREP_SEVERITY.get(str(extra.get("severity") or ""), "medium"),
            )
        )
    return out


def _parse_knip(raw: str) -> list[Candidate]:
    """knip --reporter json: {files: [...], issues: [{file, exports, types,
    duplicates, ...}]} — unused files/exports are low-severity candidates."""
    try:
        payload = json.loads(raw or "{}")
    except ValueError:
        return []
    out = []
    for f in payload.get("files") or []:
        out.append(
            Candidate(tool="knip", rule="unused-file", path=str(f), line=0,
                      message="file is never imported", severity="low")
        )
    for issue in payload.get("issues") or []:
        path = str(issue.get("file") or "")
        for kind in ("exports", "types", "duplicates", "dependencies", "devDependencies"):
            for entry in issue.get(kind) or []:
                name = entry.get("name") if isinstance(entry, dict) else entry
                line = int(entry.get("line") or 0) if isinstance(entry, dict) else 0
                out.append(
                    Candidate(tool="knip", rule=f"unused-{kind.rstrip('s')}", path=path,
                              line=line, message=f"unused {kind.rstrip('s')}: {name}",
                              severity="low")
                )
    return out


# ── Registry ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AnalyzerSpec:
    argv: tuple[str, ...]  # extended with user args; runs with cwd=workspace
    parse: callable
    ok_exit_codes: tuple[int, ...]  # linters exit non-zero on findings


ANALYZERS: dict[str, AnalyzerSpec] = {
    "ruff": AnalyzerSpec(("ruff", "check", "--output-format", "json", "--exit-zero", "."), _parse_ruff, (0,)),
    "vulture": AnalyzerSpec(("vulture", "."), _parse_vulture, (0, 3)),
    "deptry": AnalyzerSpec(("deptry", ".", "--json-output", "/dev/stdout"), _parse_deptry, (0, 1)),
    "semgrep": AnalyzerSpec(("semgrep", "scan", "--json", "--quiet"), _parse_semgrep, (0, 1)),
    "knip": AnalyzerSpec(("knip", "--reporter", "json", "--no-exit-code"), _parse_knip, (0,)),
}


def detect_default_tools(workspace_path: str) -> list[dict]:
    """Ecosystem sniff for mode=auto. semgrep is never auto-enabled (it
    needs an explicit ruleset choice)."""
    root = Path(workspace_path)
    tools: list[dict] = []
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        tools += [{"tool": "ruff"}, {"tool": "vulture"}, {"tool": "deptry"}]
    if (root / "package.json").exists():
        tools.append({"tool": "knip"})
    return tools


def resolve_tools(config: dict | None, workspace_path: str) -> list[dict]:
    """Honor the repo's analyzer config: off → [], custom → its list
    (unknown tool names dropped), auto/unset → ecosystem detection."""
    cfg = dict(config or {})
    mode = str(cfg.get("mode") or "auto")
    if mode == "off":
        return []
    if mode == "custom":
        return [dict(t) for t in cfg.get("tools") or [] if (t or {}).get("tool") in ANALYZERS]
    return detect_default_tools(workspace_path)


async def run_analyzers(
    *,
    workspace_path: str,
    tools: list[dict],
    timeout_seconds: int | None = None,
) -> AnalyzerReport:
    """Run each configured tool in the workspace. Missing binaries, crashes,
    and timeouts become skip notes — never exceptions."""
    timeout = timeout_seconds or settings.OPENSWEEP_ANALYZER_TIMEOUT_SECONDS
    report = AnalyzerReport()
    for entry in tools:
        name = str(entry.get("tool") or "")
        spec = ANALYZERS.get(name)
        if spec is None:
            report.tools_skipped.append({"tool": name, "reason": "unknown tool"})
            continue
        if not shutil.which(spec.argv[0]):
            report.tools_skipped.append({"tool": name, "reason": "not installed"})
            continue
        argv = list(spec.argv) + [str(a) for a in entry.get("args") or []]
        argv += [str(p) for p in entry.get("paths") or []]
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            report.tools_skipped.append({"tool": name, "reason": f"timed out after {timeout}s"})
            continue
        except Exception as exc:  # noqa: BLE001 — analyzer failure never fails the run
            report.tools_skipped.append({"tool": name, "reason": f"{type(exc).__name__}: {exc}"})
            continue
        raw = stdout.decode("utf-8", "replace")
        report.raw_outputs[name] = raw or stderr.decode("utf-8", "replace")
        if proc.returncode not in spec.ok_exit_codes:
            report.tools_skipped.append(
                {"tool": name, "reason": f"exit code {proc.returncode}"}
            )
            continue
        try:
            report.candidates.extend(spec.parse(raw))
        except Exception as exc:  # noqa: BLE001
            report.tools_skipped.append({"tool": name, "reason": f"parse failed: {exc}"})
            continue
        report.tools_run.append(name)
    return report


def filter_candidates(
    candidates: list[Candidate], *, allowed_paths: list[str] | None
) -> list[Candidate]:
    """Keep candidates under the given path prefixes (diff files for reviews,
    watch_paths for audits). No prefixes = no filter."""
    if not allowed_paths:
        return list(candidates)
    from domains.docs.services.doc_freshness import watches_path

    return [c for c in candidates if watches_path(allowed_paths, c.path)]


def render_candidates_section(
    report: AnalyzerReport, *, cap: int | None = None, artifact_uri: str = ""
) -> str:
    """The markdown block appended to the run context. Empty string when
    there is nothing to say (no tools ran and nothing was skipped)."""
    if not report.candidates and not report.tools_run and not report.tools_skipped:
        return ""
    cap = cap or settings.OPENSWEEP_ANALYZER_MAX_CANDIDATES
    ranked = sorted(
        report.candidates,
        key=lambda c: (_SEVERITIES.index(c.severity) if c.severity in _SEVERITIES else 1, c.path, c.line),
    )
    shown = ranked[:cap]
    lines = [
        "## Static-analysis candidates (deterministic tools — investigate, do not copy)",
        "",
        "Configured analyzers ran over this workspace before you started. Each line is",
        "a CANDIDATE, not a confirmed problem: investigate the ones relevant to your",
        "scope, file a Finding only where you can evidence a real issue, and ignore",
        "false positives silently. Do not re-run these tools.",
        "",
        "When you file a Finding for a candidate, pass its tool and rule as",
        "`detected_by_tool` (e.g. `semgrep`) and `detected_by_rule` (the rule/check",
        "id) so the finding is traceable back to the analyzer that surfaced it.",
        "Each candidate below is formatted `[severity] <tool> <rule> — location — message`.",
        "",
    ]
    if not shown:
        lines.append("(analyzers ran clean — no candidates)")
    for c in shown:
        loc = f"{c.path}:{c.line}" if c.line else c.path
        lines.append(f"- [{c.severity}] {c.tool} {c.rule} — {loc} — {c.message}")
    if len(ranked) > len(shown):
        suffix = f" — full output: {artifact_uri}" if artifact_uri else ""
        lines.append(f"({len(shown)} of {len(ranked)} candidates shown{suffix})")
    elif artifact_uri:
        lines.append(f"(full output: {artifact_uri})")
    for s in report.tools_skipped:
        lines.append(f"(skipped: {s['tool']} — {s['reason']})")
    return "\n".join(lines)


def report_to_json(report: AnalyzerReport) -> str:
    """Artifact payload: normalized candidates + skip notes + raw output."""
    return json.dumps(
        {
            "tools_run": report.tools_run,
            "tools_skipped": report.tools_skipped,
            "candidates": [c.__dict__ for c in report.candidates],
            "raw_outputs": report.raw_outputs,
        },
        indent=2,
    )


async def diff_paths(workspace_path: str, base_ref: str, head_ref: str) -> list[str]:
    """Changed files of the PR (for candidate scoping) — [] on any failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "--name-only", f"origin/{base_ref}...{head_ref}",
            cwd=workspace_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            return []
        return [ln.strip() for ln in stdout.decode("utf-8", "replace").splitlines() if ln.strip()]
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"diff-paths failed in {workspace_path}: {exc}", extra={"tag": "analysis"})
        return []
