# Thread Terminal Takeover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Continue in terminal" button on Threads that copies a one-paste command handing the live agent conversation over to the user's local terminal — resuming the actual Claude Code session (3A) when possible, seeding a fresh session from a handoff brief written into the workspace (3B) otherwise.

**Architecture:** Sandboxes are host-filesystem git clones at `~/.opensweep/sandboxes/<uid>` (container path `/host/sandboxes/<uid>`), and the worker container already bind-mounts the host `~/.claude`, so executor session files are host-visible. A new `POST /api/v1/runs/{uid}/handoff` endpoint prepares the takeover (writes an `OPENSWEEP_HANDOFF.md` brief into the sandbox, builds the paste command) and returns a DTO the frontend copies to the clipboard. The only infra change is also mounting `~/.claude` into the backend container so follow-up-turn sessions land in the same host store.

**Tech Stack:** FastAPI + neomodel (Neo4j), pytest (pure tests, no DB), Vue 3 + TypeScript + Pinia.

## Global Constraints

- Backend tests: `cd back_end && uv run pytest <file> -v`. Pure tests only — no Neo4j dependence (repo convention; `tests/conftest.py` skips DB tests unless Neo4j is reachable).
- Frontend check: `cd front_end && npm run type-check`.
- Never put platform secrets in agent-visible files or the returned command (§13 discipline in `domains/executors/agent_env.py`).
- Handoff file name is exactly `OPENSWEEP_HANDOFF.md`, written at the sandbox root and excluded via `.git/info/exclude` (never a tracked file).
- Verified facts this plan relies on (do not re-derive):
  - Claude Code stores sessions at `~/.claude/projects/<slug>/<session-id>.jsonl` where `<slug>` is the **resolved** cwd with every non-alphanumeric char replaced by `-` (verified on this machine: `/Users/jeroenbrouns/.claude/...` → `-Users-jeroenbrouns--claude-...`; `/tmp/x` resolves to `/private/tmp/x` first).
  - `claude --resume <session-id>` is **project-scoped**: it only finds sessions under the current cwd's slug. Copying the session `.jsonl` into the target cwd's slug directory makes resume work there (verified empirically end-to-end).
  - Sandbox `container_path` = `/host/sandboxes/<uid>` (settings `OPENSWEEP_SANDBOX_HOST_MOUNT`), `host_path` = `~/.opensweep/sandboxes/<uid>` (settings `OPENSWEEP_SANDBOX_HOST_PATH`, tilde left unexpanded — the user's shell expands it).
  - First turns run in the Celery worker (mounts `${HOME}/.claude:/root/.claude`); follow-up turns run in the backend container (no such mount today — Task 4 adds it).

---

### Task 1: Pure handoff helpers

**Files:**
- Create: `back_end/domains/investigations/services/handoff.py`
- Test: `back_end/tests/test_handoff_pure.py`

**Interfaces:**
- Produces: `HANDOFF_FILENAME: str`, `claude_project_slug(path: str) -> str`, `handoff_mode(*, executor: str, cli_session_id: str, sandbox_live: bool) -> tuple[str, str]`, `build_resume_command(*, host_path: str, container_path: str, cli_session_id: str) -> str`, `build_seeded_command(*, host_path: str) -> str`, `render_handoff_markdown(*, title: str, playbook: str, work_branch: str, base_branch: str, entries: list[dict], cap: int = 20000) -> str`. Task 2 and 3 consume all of these.

- [ ] **Step 1: Write the failing tests**

```python
"""Pure tests for the terminal-handoff helpers (no Neo4j, no filesystem)."""

from domains.investigations.services.handoff import (
    HANDOFF_FILENAME,
    build_resume_command,
    build_seeded_command,
    claude_project_slug,
    handoff_mode,
    render_handoff_markdown,
)


def test_slug_replaces_every_non_alphanumeric_char():
    assert claude_project_slug("/host/sandboxes/abc123") == "-host-sandboxes-abc123"
    # Dots and underscores are NOT preserved — matches ~/.claude/projects layout.
    assert claude_project_slug("/Users/j/.opensweep/x_y") == "-Users-j--opensweep-x-y"
    assert claude_project_slug("") == ""


def test_mode_resume_needs_claude_session_and_live_sandbox():
    assert handoff_mode(executor="claude_code", cli_session_id="abc", sandbox_live=True) == ("resume", "")


def test_mode_seeded_for_other_executors_or_missing_session():
    mode, _ = handoff_mode(executor="codex", cli_session_id="abc", sandbox_live=True)
    assert mode == "seeded"
    mode, _ = handoff_mode(executor="claude_code", cli_session_id="", sandbox_live=True)
    assert mode == "seeded"


def test_mode_unavailable_without_workspace_explains_recovery():
    mode, reason = handoff_mode(executor="claude_code", cli_session_id="abc", sandbox_live=False)
    assert mode == "unavailable"
    assert "rebuild" in reason


def test_resume_command_copies_session_into_host_slug_then_resumes():
    cmd = build_resume_command(
        host_path="~/.opensweep/sandboxes/abc123",
        container_path="/host/sandboxes/abc123",
        cli_session_id="11111111-2222-3333-4444-555555555555",
    )
    assert cmd.startswith("cd ~/.opensweep/sandboxes/abc123 && ")
    # Source: the slug the CONTAINER cwd produced; destination: computed on the
    # host from the resolved cwd, so it is correct for any host home/symlinks.
    assert "-host-sandboxes-abc123" in cmd
    assert "pwd -P" in cmd
    assert cmd.rstrip().endswith("claude --resume 11111111-2222-3333-4444-555555555555")


def test_seeded_command_points_claude_at_the_handoff_file():
    cmd = build_seeded_command(host_path="~/.opensweep/sandboxes/abc123")
    assert cmd.startswith("cd ~/.opensweep/sandboxes/abc123 && claude ")
    assert HANDOFF_FILENAME in cmd


def test_handoff_markdown_carries_context_and_guardrails():
    md = render_handoff_markdown(
        title="Fix flaky retry test",
        playbook="thread",
        work_branch="opensweep/t-1",
        base_branch="main",
        entries=[
            {"role": "user", "content": "please fix the retry test"},
            {"role": "assistant", "content": "I found the race in ..."},
        ],
    )
    assert "Fix flaky retry test" in md
    assert "opensweep/t-1" in md and "main" in md
    assert "please fix the retry test" in md
    assert "do not switch branches" in md.lower()


def test_handoff_markdown_caps_transcript_keeping_the_tail():
    entries = [{"role": "user", "content": "x" * 30000}, {"role": "assistant", "content": "THE-TAIL"}]
    md = render_handoff_markdown(
        title="t", playbook="thread", work_branch="w", base_branch="b", entries=entries, cap=5000
    )
    assert "THE-TAIL" in md
    assert len(md) < 12000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd back_end && uv run pytest tests/test_handoff_pure.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domains.investigations.services.handoff'`

- [ ] **Step 3: Write the implementation**

```python
"""Terminal takeover of a run's conversation (docs/features/sandbox_improvements.md §3A/3B).

Sandboxes are host-filesystem clones and the agent containers bind-mount the
host ~/.claude, so a conversation can be handed to the user's own terminal:

- resume (3A): claude_code runs with a cli_session_id — the session .jsonl
  already sits in the host's ~/.claude/projects under the CONTAINER cwd slug
  (/host/sandboxes/<uid>). The command copies it under the HOST cwd slug
  (claude resume is project-scoped) and runs `claude --resume <id>`.
- seeded (3B): other executors / missing session — a fresh local claude is
  pointed at OPENSWEEP_HANDOFF.md, written into the sandbox by prepare_handoff.

Everything in this module is pure string/markdown construction so it stays
unit-testable; filesystem + DB side effects live in prepare_handoff (Task 2).
"""

from __future__ import annotations

import re

HANDOFF_FILENAME = "OPENSWEEP_HANDOFF.md"

# Transcript tail budget for the handoff brief — enough to carry the working
# context without turning the file into a novel; claude reads the repo anyway.
HANDOFF_TRANSCRIPT_CAP = 20_000


def claude_project_slug(path: str) -> str:
    """Claude Code's project-directory name for a cwd: every char outside
    [A-Za-z0-9] becomes '-' (verified against ~/.claude/projects layout)."""
    return re.sub(r"[^A-Za-z0-9]", "-", path or "")


def handoff_mode(*, executor: str, cli_session_id: str, sandbox_live: bool) -> tuple[str, str]:
    """(mode, reason): resume | seeded | unavailable — reason set only when
    unavailable, phrased as the recovery action."""
    if not sandbox_live:
        return (
            "unavailable",
            "workspace destroyed — send a message in the conversation to rebuild it, then retry",
        )
    if executor == "claude_code" and cli_session_id:
        return "resume", ""
    return "seeded", ""


def build_resume_command(*, host_path: str, container_path: str, cli_session_id: str) -> str:
    """One-paste 3A command. The destination slug is computed ON THE HOST from
    the resolved cwd (`pwd -P` — macOS /tmp-style symlinks would break a
    precomputed slug), so the backend never needs to know the host home. cp -n
    keeps an already-copied (possibly newer) session file intact; its stderr is
    silenced so a missing source degrades to claude's own clear error."""
    src_slug = claude_project_slug(container_path)
    return (
        f"cd {host_path} && "
        "dst=\"$HOME/.claude/projects/$(pwd -P | sed 's/[^a-zA-Z0-9]/-/g')\" && "
        'mkdir -p "$dst" && '
        f'cp -n "$HOME/.claude/projects/{src_slug}/{cli_session_id}.jsonl" "$dst/" 2>/dev/null; '
        f"claude --resume {cli_session_id}"
    )


def build_seeded_command(*, host_path: str) -> str:
    """One-paste 3B command: fresh claude, seeded by the handoff brief."""
    return (
        f"cd {host_path} && claude "
        f'"Read {HANDOFF_FILENAME} at the repository root first — it hands over an '
        'OpenSweep agent conversation — then continue that work."'
    )


def render_handoff_markdown(
    *,
    title: str,
    playbook: str,
    work_branch: str,
    base_branch: str,
    entries: list[dict],
    cap: int = HANDOFF_TRANSCRIPT_CAP,
) -> str:
    """The OPENSWEEP_HANDOFF.md brief: what the conversation was, the branch
    contract, and the transcript tail. Written for the LOCAL agent — platform
    push validation no longer applies, but the branch contract still does so
    the platform can pick the conversation back up."""
    lines = [f"{e.get('role', '?')}: {e.get('content', '')}" for e in entries]
    transcript = "\n\n".join(lines)
    if len(transcript) > cap:
        transcript = transcript[-cap:]
        cut = transcript.find("\n")
        if cut != -1:
            transcript = transcript[cut + 1 :]
    return f"""# OpenSweep conversation handoff

You are taking over an OpenSweep agent conversation in a local terminal.

- **Task:** {title or "(untitled run)"} (playbook: {playbook or "?"})
- **Work branch:** `{work_branch}` (based on `{base_branch}`)

## Ground rules

- Stay on `{work_branch}` — do not switch branches or rewrite history you
  did not create. Commits you make here are picked up when the conversation
  resumes on the platform (same working copy).
- You are running under the USER's own credentials now: pushing is allowed,
  but committing locally and letting the platform deliver is the default.
- This file is untracked and ignored — never commit it.

## Conversation so far (tail)

{transcript}
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd back_end && uv run pytest tests/test_handoff_pure.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add back_end/domains/investigations/services/handoff.py back_end/tests/test_handoff_pure.py
git commit -m "feat: pure helpers for terminal takeover of run conversations"
```

---

### Task 2: Handoff preparation (filesystem side effects + DTO assembly)

**Files:**
- Modify: `back_end/domains/investigations/services/handoff.py` (append)
- Modify: `back_end/domains/investigations/schemas.py` (append DTO)
- Test: `back_end/tests/test_handoff_prepare.py`

**Interfaces:**
- Consumes: Task 1 helpers; `transcript_entries(run_uid)` from `domains.investigations.services.turn_service`; `Sandbox` model + `SandboxStatus` from `domains.execution`.
- Produces: `RunHandoffDTO(mode, command, sandbox_host_path, cli_session_id, reason)` in `domains/investigations/schemas.py`; `write_handoff_file(sandbox_dir: str, content: str) -> str` and `async prepare_handoff(run) -> RunHandoffDTO` in `handoff.py`. Task 3 consumes both.

- [ ] **Step 1: Write the failing tests**

```python
"""Filesystem side of the terminal handoff — tmp_path stands in for a sandbox."""

from pathlib import Path

from domains.investigations.services.handoff import HANDOFF_FILENAME, write_handoff_file


def _fake_sandbox(tmp_path: Path) -> Path:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    return tmp_path


def test_write_handoff_file_creates_brief_and_git_exclude(tmp_path):
    sandbox = _fake_sandbox(tmp_path)
    path = write_handoff_file(str(sandbox), "# brief")
    assert Path(path).read_text() == "# brief"
    assert Path(path).name == HANDOFF_FILENAME
    exclude = (sandbox / ".git" / "info" / "exclude").read_text()
    assert HANDOFF_FILENAME in exclude


def test_write_handoff_file_is_idempotent_on_exclude(tmp_path):
    sandbox = _fake_sandbox(tmp_path)
    write_handoff_file(str(sandbox), "one")
    write_handoff_file(str(sandbox), "two")
    exclude = (sandbox / ".git" / "info" / "exclude").read_text()
    assert exclude.count(HANDOFF_FILENAME) == 1
    assert (sandbox / HANDOFF_FILENAME).read_text() == "two"


def test_write_handoff_file_survives_missing_git_dir(tmp_path):
    # A half-destroyed sandbox must not break the handoff response.
    path = write_handoff_file(str(tmp_path), "# brief")
    assert Path(path).read_text() == "# brief"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd back_end && uv run pytest tests/test_handoff_prepare.py -v`
Expected: FAIL — `ImportError: cannot import name 'write_handoff_file'`

- [ ] **Step 3: Append implementation to `handoff.py`**

```python
# ── Side effects (Task 2) ────────────────────────────────────────────────────

from pathlib import Path  # noqa: E402  (module-top in the real file)


def write_handoff_file(sandbox_dir: str, content: str) -> str:
    """Write the brief at the sandbox root and keep it out of git via
    .git/info/exclude (idempotent). The exclude write is best-effort — a
    sandbox mid-teardown must not break the handoff response."""
    root = Path(sandbox_dir)
    path = root / HANDOFF_FILENAME
    path.write_text(content)
    try:
        exclude = root / ".git" / "info" / "exclude"
        if exclude.parent.is_dir():
            existing = exclude.read_text() if exclude.exists() else ""
            if HANDOFF_FILENAME not in existing.splitlines():
                with exclude.open("a") as fh:
                    fh.write(f"{HANDOFF_FILENAME}\n")
    except OSError:
        pass
    return str(path)


async def prepare_handoff(run) -> "RunHandoffDTO":
    """Build the takeover payload for a run: pick the mode, write the brief
    into the live sandbox, and render the one-paste command."""
    from domains.execution.models import Sandbox
    from domains.execution.schemas import SandboxStatus
    from domains.investigations.schemas import RunHandoffDTO
    from domains.investigations.services.turn_service import transcript_entries

    sandbox = (
        await Sandbox.nodes.get_or_none(uid=run.sandbox_uid) if (run.sandbox_uid or "") else None
    )
    live = sandbox is not None and sandbox.status == SandboxStatus.READY.value
    mode, reason = handoff_mode(
        executor=run.executor or "",
        cli_session_id=run.cli_session_id or "",
        sandbox_live=live,
    )
    if mode == "unavailable":
        return RunHandoffDTO(mode=mode, reason=reason)

    spec = dict(run.workspace_spec or {})
    content = render_handoff_markdown(
        title=run.title or "",
        playbook=run.playbook or "",
        work_branch=spec.get("work_branch") or sandbox.sandbox_branch or "",
        base_branch=spec.get("base_branch") or sandbox.source_branch or "",
        entries=transcript_entries(run.uid),
    )
    # Written in BOTH modes: if a resume ever fails (custom CLAUDE_CONFIG_DIR,
    # pruned session), the brief is already in place as the fallback.
    write_handoff_file(sandbox.container_path, content)

    if mode == "resume":
        command = build_resume_command(
            host_path=sandbox.host_path,
            container_path=sandbox.container_path,
            cli_session_id=run.cli_session_id,
        )
    else:
        command = build_seeded_command(host_path=sandbox.host_path)
    return RunHandoffDTO(
        mode=mode,
        command=command,
        sandbox_host_path=sandbox.host_path,
        cli_session_id=run.cli_session_id or "",
    )
```

(Consolidate imports at module top in the real file: `from pathlib import Path` joins `import re`.)

- [ ] **Step 4: Append `RunHandoffDTO` to `back_end/domains/investigations/schemas.py`**

Place it next to the other response DTOs (after `RunDTO`-adjacent classes; match the file's `BaseModel` style):

```python
class RunHandoffDTO(BaseModel):
    """Terminal takeover payload (docs/features/sandbox_improvements.md §3A/3B).

    mode: resume — paste-command resumes the actual claude session;
          seeded — paste-command starts a fresh claude seeded by the
          OPENSWEEP_HANDOFF.md brief written into the workspace;
          unavailable — no live workspace; `reason` says how to recover.
    """

    mode: str
    command: str = ""
    sandbox_host_path: str = ""
    cli_session_id: str = ""
    reason: str = ""
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd back_end && uv run pytest tests/test_handoff_prepare.py tests/test_handoff_pure.py -v`
Expected: PASS (11 tests)

- [ ] **Step 6: Commit**

```bash
git add back_end/domains/investigations/services/handoff.py back_end/domains/investigations/schemas.py back_end/tests/test_handoff_prepare.py
git commit -m "feat: handoff preparation — brief file, git exclude, RunHandoffDTO"
```

---

### Task 3: `POST /runs/{uid}/handoff` endpoint + timeline events

**Files:**
- Modify: `back_end/api/v1/runs.py` (add route after `end_run`, ~line 543)

**Interfaces:**
- Consumes: `prepare_handoff(run)` + `RunHandoffDTO` (Task 2); `append_event` from `run_events`; `ThreadService.record_event`; existing route deps (`require_role`, `require_repo_in_org`, `write_audit` — all already imported or importable in `runs.py`; check the file's existing imports and reuse them).
- Produces: `POST /api/v1/runs/{uid}/handoff` → `RunHandoffDTO`, operation_id `opensweep_run_handoff`. Task 5's store action calls this.

- [ ] **Step 1: Add the route (follow the `end_run` pattern directly above it)**

```python
@router.post("/{uid}/handoff", response_model=RunHandoffDTO, operation_id="opensweep_run_handoff")
async def handoff_run(uid: str, user: UserDTO = Depends(require_role("maintainer"))):
    """Hand the conversation to the user's local terminal: write the
    OPENSWEEP_HANDOFF.md brief into the live workspace and return the
    one-paste command (resume the CLI session when possible, seed a fresh
    one otherwise). The run stays awaiting_input — takeover is recorded on
    the timeline, not enforced as a lock; local commits land in the same
    working copy the next platform turn reads."""
    from domains.investigations.services.handoff import prepare_handoff

    service = TurnService()
    run = await service.get_run(uid)
    await require_repo_in_org(run.repository_uid, user.org_uid)
    dto = await prepare_handoff(run)
    if dto.mode != "unavailable":
        append_event(
            uid,
            "system",
            kind="terminal_takeover",
            text="conversation handed to a local terminal",
        )
        if getattr(run, "thread_uid", "") or "":
            try:
                from domains.threads.services.thread_service import ThreadService

                svc = ThreadService()
                thread = await svc.get_node(run.thread_uid)
                await svc.record_event(thread, "terminal_takeover", run_uid=uid, by=user.uid)
            except Exception as exc:  # noqa: BLE001 — timeline is best-effort
                logger.warning(
                    f"thread terminal_takeover event failed for run {uid}: {exc}",
                    extra={"tag": "runs"},
                )
        await write_audit(
            kind="run.handoff", subject_uid=uid, subject_type="Run", actor_uid=user.uid
        )
    return dto
```

Add `RunHandoffDTO` to the existing `domains.investigations.schemas` import block in `runs.py`. Verify `append_event`, `write_audit`, and `logger` are already imported there (they are used by neighboring routes; if any is missing, import it the way sibling modules do).

- [ ] **Step 2: Verify the app still imports and the full suite passes**

Run: `cd back_end && uv run pytest -q`
Expected: all tests pass (1165 baseline + 11 new), no import errors. `tests/test_mcp_surface.py` guards the platform-tool MCP surface — a plain REST route must not change it; if it fails, the route was registered wrong.

- [ ] **Step 3: Commit**

```bash
git add back_end/api/v1/runs.py
git commit -m "feat: POST /runs/{uid}/handoff — terminal takeover endpoint"
```

---

### Task 4: Share the Claude session store with the backend container

**Files:**
- Modify: `docker-compose.yml` (opensweep_backend `volumes`, after the `/host/sandboxes` line ~65)

**Interfaces:**
- Produces: backend-container `claude` subprocesses read/write the host `~/.claude` — required for 3A because follow-up turns (which mint/refresh `cli_session_id`) run in the backend, and their session files must land in the store the user's terminal reads. Also fixes cross-container `--resume` (first turn writes sessions via the worker's existing mount; the backend previously resumed against its own ephemeral `/root/.claude`).

- [ ] **Step 1: Add the mount**

In the `opensweep_backend` service `volumes:` block, after the sandboxes line:

```yaml
      # Claude Code session store, shared with the HOST and the worker: follow-up
      # turns run in this container and resume by session id — the session files
      # must live in the same store the worker writes and the user's own terminal
      # reads (Continue-in-terminal handoff). On Linux hosts, files created from
      # the container are root-owned (Docker Desktop on macOS maps to the host user).
      - ${HOME}/.claude:/root/.claude:rw
```

- [ ] **Step 2: Validate compose config**

Run: `docker compose config --quiet && echo OK`
Expected: `OK` (no schema errors). Do NOT bring the stack up/down — the main checkout may be running it.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "fix: mount host ~/.claude into the backend for cross-container session resume"
```

---

### Task 5: Frontend — store action, button, ThreadView wiring

**Files:**
- Modify: `front_end/src/types/api.ts` (add `RunHandoffDTO` near the run DTOs, ~line 356 area)
- Modify: `front_end/src/stores/runStore.ts` (add `handoff` action + export)
- Create: `front_end/src/components/runs/ContinueInTerminalButton.vue`
- Modify: `front_end/src/views/ThreadView.vue` (ActionMenuBar, next to `TestLocallyButton` ~line 322)

**Interfaces:**
- Consumes: `POST /runs/{uid}/handoff` (Task 3); existing `apiPost` from `@/services/api`; `Button` (supports `:loading`), `useToast().success/error(title, message)` — same usage as `TestLocallyButton.vue`; `ApiError` from `@/services/api` (match ThreadView's import).
- Produces: `<ContinueInTerminalButton :run-uid="...">` used by ThreadView (and reusable on run detail surfaces later).

- [ ] **Step 1: Add the type to `types/api.ts`**

```typescript
/** Terminal takeover payload for POST /runs/{uid}/handoff. */
export interface RunHandoffDTO {
  /** resume — paste resumes the actual claude session; seeded — paste starts a
   *  fresh claude seeded by the OPENSWEEP_HANDOFF.md brief; unavailable — no
   *  live workspace, `reason` says how to recover. */
  mode: 'resume' | 'seeded' | 'unavailable'
  command: string
  sandbox_host_path: string
  cli_session_id: string
  reason: string
}
```

- [ ] **Step 2: Add the store action in `runStore.ts`**

Import `RunHandoffDTO` in the type-import block, then next to `interrupt`:

```typescript
  /** Prepare a terminal takeover: writes the handoff brief into the workspace
   *  and returns the one-paste command for the user's shell. */
  async function handoff(uid: string): Promise<RunHandoffDTO> {
    return apiPost<RunHandoffDTO>(`/runs/${uid}/handoff`)
  }
```

Add `handoff,` to the returned object.

- [ ] **Step 3: Create `ContinueInTerminalButton.vue`**

```vue
<script setup lang="ts">
// Hands the live agent conversation to the user's terminal: one paste either
// resumes the actual claude session (same workspace, full context) or starts a
// fresh one seeded by the OPENSWEEP_HANDOFF.md brief the backend just wrote.
import { ref } from 'vue'
import { Terminal } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { useToast } from '@/composables/useToast'
import { useRunStore } from '@/stores/runStore'
import { ApiError } from '@/services/api'

const props = defineProps<{ runUid: string }>()

const toast = useToast()
const runs = useRunStore()
const busy = ref(false)

async function takeover() {
  if (busy.value) return
  busy.value = true
  try {
    const h = await runs.handoff(props.runUid)
    if (h.mode === 'unavailable') {
      toast.error('Workspace is gone', h.reason)
      return
    }
    await navigator.clipboard.writeText(h.command)
    toast.success(
      'Terminal command copied',
      h.mode === 'resume'
        ? 'Paste it in your terminal — the agent session resumes with full context.'
        : 'Paste it in your terminal — a fresh session picks up from the handoff brief.',
    )
  } catch (e) {
    toast.error('Couldn’t prepare handoff', e instanceof ApiError ? e.detail : String(e))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Button variant="outline" size="sm" :loading="busy" @click="takeover">
    <Terminal /> Continue in terminal
  </Button>
</template>
```

(Verify ThreadView's actual `ApiError` import path first and mirror it — if it imports from elsewhere, e.g. `@/services/api` vs `@/api`, use that.)

- [ ] **Step 4: Wire into `ThreadView.vue`**

Script: `import ContinueInTerminalButton from '@/components/runs/ContinueInTerminalButton.vue'` next to the `TestLocallyButton` import. Template, inside `ActionMenuBar` directly after `TestLocallyButton`:

```vue
      <ContinueInTerminalButton
        v-if="thread.active_run_uid"
        :run-uid="thread.active_run_uid"
      />
```

- [ ] **Step 5: Type-check**

Run: `cd front_end && npm run type-check`
Expected: clean exit (0 errors)

- [ ] **Step 6: Commit**

```bash
git add front_end/src/types/api.ts front_end/src/stores/runStore.ts front_end/src/components/runs/ContinueInTerminalButton.vue front_end/src/views/ThreadView.vue
git commit -m "feat: Continue-in-terminal button on threads"
```

---

### Task 6: Docs touch-up + full verification

**Files:**
- Modify: `docs/features/sandbox_improvements.md` (§3A/3B — mark implemented, note the endpoint and button)

- [ ] **Step 1: Update the doc**

In the Track 3 section, change the "being implemented" notes on 3A/3B to implemented, adding one sentence each: 3A — `POST /api/v1/runs/{uid}/handoff` + the ThreadView "Continue in terminal" button; session files shared via the `~/.claude` bind-mounts. 3B — `OPENSWEEP_HANDOFF.md` brief written into the workspace, used for non-claude executors and as the resume fallback.

- [ ] **Step 2: Full test pass**

Run: `cd back_end && uv run pytest -q` then `cd front_end && npm run type-check`
Expected: backend all green; frontend 0 errors.

- [ ] **Step 3: Commit**

```bash
git add docs/features/sandbox_improvements.md
git commit -m "docs: mark terminal takeover (3A/3B) implemented"
```
