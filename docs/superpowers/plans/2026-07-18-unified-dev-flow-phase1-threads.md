# Unified Dev Flow — Phase 1: Threads — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A first-class Thread entity that carries one ticket through an interactive refine/plan conversation, a soft plan-approval gate, and an implement run with decision-log carry-over — surfaced in a new Thread view with unified steering and a "Test locally" button.

**Architecture:** New `threads` backend domain (neomodel node + service + FastAPI router, auto-discovered by `app.py`). The thread orchestrates existing runs: it dispatches an interactive `refine`-playbook session for plan mode, then calls the existing `trigger_implement_run(..., intent_addendum=...)` with a distilled decision log. Two small hooks (implement finalizer, merge webhook) advance thread phase. Frontend: Pinia store + ThreadView reusing `RunTranscript` + `useRunSocket`.

**Tech Stack:** FastAPI + neomodel (async, Neo4j), Celery/Redis (untouched), Vue 3 + TypeScript + Pinia, pytest.

**Spec:** `docs/superpowers/specs/2026-07-18-unified-dev-flow-design.md` (this plan covers Phase 1 only).

## Global Constraints

- Work happens in the **public repo** (`opensweep`), branch `spec/unified-dev-flow`. Never `if cloud:` branches (open-core rule, `CLAUDE.md`).
- Backend tests: `cd back_end && pytest <file> -v`. Prefer pure tests (no Neo4j); DB-dependent behavior is exercised via pure helpers, not integration tests (repo convention: `tests/conftest.py` skips DB tests unless Neo4j is reachable).
- Frontend verification: `cd front_end && npm run type-check && npm run build`. No frontend unit-test framework exists; type-check is the gate.
- uid generation: `uuid4().hex` (see `back_end/domains/tickets/services/ticket_service.py:163`).
- Timestamps: `datetime.now(UTC)` (`from datetime import UTC, datetime`).
- Every state-changing endpoint: `require_role("maintainer")` + `require_repo_in_org(...)` + `write_audit(...)` (mirror `api/v1/tickets.py`).
- Platform tool names are prefixed `opensweep_platform_`; new writer tools must be added to the allow-list assertions in `back_end/tests/test_mcp_surface.py`.
- Playbook hooks must never raise (mirror `domains/investigations/services/playbooks.py` — log warnings, don't propagate).
- Conventional commits (`feat:`, `test:`, `fix:`); commit after every task.

---

### Task 1: Thread model + phase transition matrix

**Files:**
- Create: `back_end/domains/threads/__init__.py` (empty)
- Create: `back_end/domains/threads/models.py`
- Test: `back_end/tests/test_thread_transitions.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Thread` neomodel node; constants `THREAD_PHASES`, `PLAN_STATES`, `LEGAL_PHASE_TRANSITIONS: dict[str, frozenset[str]]`; pure fn `is_legal_phase_transition(frm: str, to: str) -> bool`. Later tasks import all of these from `domains.threads.models`.

- [ ] **Step 1: Write the failing test**

```python
"""Thread phase state machine (unified dev flow Phase 1).

Pure tests, mirroring tests/test_ticket_transitions.py: the full legality
matrix spelled out pairwise so a regression in either the dict or the
checker is caught.
"""

from domains.threads.models import (
    LEGAL_PHASE_TRANSITIONS,
    PLAN_STATES,
    THREAD_PHASES,
    is_legal_phase_transition,
)

LEGAL = {
    ("refining", "implementing"),
    ("implementing", "in_review"),
    ("in_review", "done"),
    # any non-terminal phase can be abandoned
    ("refining", "abandoned"),
    ("implementing", "abandoned"),
    ("in_review", "abandoned"),
}


def test_full_phase_transition_matrix():
    for frm in THREAD_PHASES:
        for to in THREAD_PHASES:
            expected = (frm, to) in LEGAL
            assert is_legal_phase_transition(frm, to) == expected, f"{frm} → {to}"


def test_terminal_phases_have_no_exits():
    assert not LEGAL_PHASE_TRANSITIONS["done"]
    assert not LEGAL_PHASE_TRANSITIONS["abandoned"]


def test_self_transitions_are_illegal():
    for phase in THREAD_PHASES:
        assert not is_legal_phase_transition(phase, phase)


def test_vocabulary():
    assert THREAD_PHASES == {"refining", "implementing", "in_review", "done", "abandoned"}
    assert PLAN_STATES == {"none", "drafted", "approved"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd back_end && pytest tests/test_thread_transitions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domains.threads'`

- [ ] **Step 3: Write the model**

`back_end/domains/threads/models.py`:

```python
"""Thread — one piece of work moving through the pipeline, with one
conversation attached (docs/superpowers/specs/2026-07-18-unified-dev-flow-design.md).

A Thread binds a ticket (or group parent) to a continuous refine → plan →
implement conversation. It orchestrates and references Runs; it never
replaces them. Review runs stay independent — their output attaches to the
timeline. Phase only ever moves through the service so every move is
legality-checked and audited.
"""

from neomodel import (
    AsyncStructuredNode,
    DateTimeProperty,
    JSONProperty,
    StringProperty,
)


class Thread(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)
    repository_uid = StringProperty(required=True, index=True)
    subject_ticket_uid = StringProperty(required=True, index=True)

    # refining | implementing | in_review | done | abandoned
    phase = StringProperty(default="refining", index=True)

    # Soft plan gate: none | drafted | approved. Approval is NOT required to
    # implement; an approved plan is injected into the implement run context.
    plan_state = StringProperty(default="none")
    plan_text = StringProperty(default="")
    plan_approved_by = StringProperty(default="")
    plan_approved_at = DateTimeProperty()

    # Delivery links, filled as the flow progresses.
    branch = StringProperty(default="")
    pr_uid = StringProperty(default="", index=True)

    # Conversation: ordered run uids + the run currently accepting messages.
    run_uids = JSONProperty(default=[])
    active_run_uid = StringProperty(default="")

    # Timeline events: [{ts, type, ...payload}] — phase_changed, plan_drafted,
    # plan_approved, run_attached, pr_opened, merged, abandoned.
    events = JSONProperty(default=[])

    created_by = StringProperty(default="")
    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)


THREAD_PHASES = {"refining", "implementing", "in_review", "done", "abandoned"}

PLAN_STATES = {"none", "drafted", "approved"}

LEGAL_PHASE_TRANSITIONS: dict[str, frozenset[str]] = {
    "refining": frozenset({"implementing", "abandoned"}),
    "implementing": frozenset({"in_review", "abandoned"}),
    "in_review": frozenset({"done", "abandoned"}),
    "done": frozenset(),
    "abandoned": frozenset(),
}


def is_legal_phase_transition(frm: str, to: str) -> bool:
    return to in LEGAL_PHASE_TRANSITIONS.get(frm, frozenset())
```

Also create empty `back_end/domains/threads/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd back_end && pytest tests/test_thread_transitions.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add back_end/domains/threads back_end/tests/test_thread_transitions.py
git commit -m "feat: Thread model + phase transition matrix"
```

---

### Task 2: `thread_uid` back-reference on Run

**Files:**
- Modify: `back_end/domains/investigations/models.py` (Run class, after `linked_finding_uid` at ~line 105)
- Test: `back_end/tests/test_thread_run_link.py`

**Interfaces:**
- Consumes: `Run` (existing).
- Produces: `Run.thread_uid: StringProperty(default="", index=True)`. Hooks in Task 8 resolve a run's thread via this field. Additive; no migration needed (neomodel default applies to old nodes on read).

- [ ] **Step 1: Write the failing test**

```python
"""Run carries an optional thread back-reference (unified dev flow Phase 1)."""

from domains.investigations.models import Run


def test_run_has_thread_uid_property():
    # neomodel classes expose deflated property definitions on the class.
    assert "thread_uid" in Run.defined_properties(rels=False, aliases=False)


def test_thread_uid_defaults_to_empty():
    prop = Run.defined_properties(rels=False, aliases=False)["thread_uid"]
    assert prop.default == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd back_end && pytest tests/test_thread_run_link.py -v`
Expected: FAIL — `KeyError`/assertion: `'thread_uid' not in ...`

- [ ] **Step 3: Add the property**

In `back_end/domains/investigations/models.py`, inside `class Run`, directly below `linked_finding_uid`:

```python
    # Set when a Thread dispatched (or adopted) this run — reverse lookup for
    # thread hooks (unified dev flow Phase 1). "" for standalone runs.
    thread_uid = StringProperty(default="", index=True)
```

- [ ] **Step 4: Run test + the existing investigations tests**

Run: `cd back_end && pytest tests/test_thread_run_link.py tests/test_investigation_vocabulary.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add back_end/domains/investigations/models.py back_end/tests/test_thread_run_link.py
git commit -m "feat: thread_uid back-reference on Run"
```

---

### Task 3: Decision-log builder (pure)

**Files:**
- Create: `back_end/domains/threads/services/__init__.py` (empty)
- Create: `back_end/domains/threads/services/decision_log.py`
- Test: `back_end/tests/test_thread_decision_log.py`

**Interfaces:**
- Consumes: transcript event dicts as produced by `domains/investigations/services/run_events.py` (`append_event` writes `{"seq", "ts", "turn", "type", ...payload}`; user turns are `type == "user_message"` with `text`, assistant prose is `type == "assistant_text"` with `text` — see `front_end/src/components/runs/RunTranscript.vue:36-44` for the consumer contract).
- Produces: `build_decision_log(events: list[dict], max_chars: int = 8000) -> str` — markdown decision log. Task 7 calls it with `read_events(run_uid)` output.

- [ ] **Step 1: Write the failing test**

```python
"""Decision-log distillation: planning conversation in, markdown log out.

Deterministic v1 (spec: 'structured carry-over always'): every user message
is a decision/answer worth carrying verbatim; the final assistant message is
the agent's own closing summary. Tool spam is excluded.
"""

from domains.threads.services.decision_log import build_decision_log


def _ev(type: str, text: str, seq: int) -> dict:
    return {"seq": seq, "ts": "2026-07-18T10:00:00Z", "turn": 1, "type": type, "text": text}


def test_includes_all_user_messages_in_order():
    events = [
        _ev("user_message", "Use Redis pub/sub, not polling", 1),
        _ev("assistant_text", "Understood. Should the gate be soft?", 2),
        _ev("user_message", "Yes, soft gate", 3),
    ]
    log = build_decision_log(events)
    assert log.index("Use Redis pub/sub") < log.index("Yes, soft gate")


def test_includes_only_final_assistant_text():
    events = [
        _ev("assistant_text", "First thought", 1),
        _ev("user_message", "ok", 2),
        _ev("assistant_text", "Final summary of the plan", 3),
    ]
    log = build_decision_log(events)
    assert "Final summary of the plan" in log
    assert "First thought" not in log


def test_excludes_tool_events():
    events = [
        _ev("user_message", "go", 1),
        {"seq": 2, "ts": "", "turn": 1, "type": "tool_use", "name": "read_doc", "input": {}},
    ]
    log = build_decision_log(events)
    assert "read_doc" not in log


def test_empty_events_gives_empty_string():
    assert build_decision_log([]) == ""


def test_truncates_oldest_first_when_over_budget():
    events = [
        _ev("user_message", "OLD " * 100, 1),
        _ev("user_message", "KEEP-THIS-RECENT-DECISION", 2),
    ]
    log = build_decision_log(events, max_chars=120)
    assert "KEEP-THIS-RECENT-DECISION" in log
    assert len(log) <= 200  # header + budgeted body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd back_end && pytest tests/test_thread_decision_log.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`back_end/domains/threads/services/decision_log.py`:

```python
"""Distill a planning conversation into a decision log for carry-over.

Deterministic: user messages are the decisions (kept verbatim, oldest first);
the final assistant_text is the agent's closing summary. When over budget,
drop the OLDEST user messages first — recent decisions supersede old ones.
"""

from __future__ import annotations

HEADER = "## Decisions from the planning conversation\n"


def build_decision_log(events: list[dict], max_chars: int = 8000) -> str:
    user_msgs = [
        (e.get("text") or "").strip()
        for e in events
        if e.get("type") == "user_message" and (e.get("text") or "").strip()
    ]
    assistant_texts = [
        (e.get("text") or "").strip()
        for e in events
        if e.get("type") == "assistant_text" and (e.get("text") or "").strip()
    ]
    if not user_msgs and not assistant_texts:
        return ""

    blocks: list[str] = [f"- (user) {m}" for m in user_msgs]
    if assistant_texts:
        blocks.append(f"- (agent, closing summary) {assistant_texts[-1]}")

    # Budget: keep the tail (most recent), drop oldest blocks first.
    kept: list[str] = []
    total = 0
    for block in reversed(blocks):
        if total + len(block) + 1 > max_chars:
            break
        kept.append(block)
        total += len(block) + 1
    return HEADER + "\n".join(reversed(kept))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd back_end && pytest tests/test_thread_decision_log.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add back_end/domains/threads/services back_end/tests/test_thread_decision_log.py
git commit -m "feat: decision-log distillation for thread carry-over"
```

---

### Task 4: Intent builders — interactive plan-mode prompt + implement addendum (pure)

**Files:**
- Create: `back_end/domains/threads/services/intents.py`
- Test: `back_end/tests/test_thread_intents.py`

**Interfaces:**
- Consumes: a `Ticket` node (duck-typed: `.uid`, `.title`, `.description`, `.acceptance_criteria`, `.priority`).
- Produces:
  - `build_thread_session_intent(ticket, thread_uid: str) -> str` — first-turn prompt for the interactive refine/plan session (Task 6 passes it to `trigger_run` via `compose_playbook_intent(custom_intent=...)`).
  - `build_implement_addendum(plan_text: str, decision_log: str) -> str` — appended to the implement intent via `trigger_implement_run(intent_addendum=...)` (Task 7).

- [ ] **Step 1: Write the failing test**

```python
"""Thread intent builders (style mirror: tests/test_implement_run_intent.py)."""

from types import SimpleNamespace

from domains.threads.services.intents import (
    build_implement_addendum,
    build_thread_session_intent,
)


def _ticket():
    return SimpleNamespace(
        uid="t-1",
        title="Fix token refresh",
        description="Refresh tokens expire early",
        acceptance_criteria=["tokens refresh silently"],
        priority="high",
    )


def test_session_intent_is_interactive_and_read_only():
    intent = build_thread_session_intent(_ticket(), "th-1")
    assert "one question at a time" in intent
    assert "read-only" in intent
    assert "t-1" in intent and "th-1" in intent


def test_session_intent_names_the_plan_tool():
    intent = build_thread_session_intent(_ticket(), "th-1")
    assert "opensweep_platform_submit_thread_plan" in intent
    assert "opensweep_platform_update_ticket" in intent


def test_addendum_contains_plan_and_decisions():
    out = build_implement_addendum("## Plan\n1. do X", "## Decisions\n- (user) soft gate")
    assert "## Plan" in out and "soft gate" in out
    assert out.index("Plan") < out.index("Decisions")


def test_addendum_empty_when_nothing_to_carry():
    assert build_implement_addendum("", "") == ""


def test_addendum_plan_only():
    out = build_implement_addendum("## Plan\n1. do X", "")
    assert "## Plan" in out and "Decisions" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd back_end && pytest tests/test_thread_intents.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`back_end/domains/threads/services/intents.py`:

```python
"""First-turn prompts for thread sessions + implement carry-over addendum.

The session prompt reuses the read-only `refine` playbook but turns it into
plan mode: interrogate the user through the conversation, ground the ticket
in code, then persist the plan via the platform tools. Prompt-building is
pure so it stays testable without a DB (mirror: api/v1/tickets.py
_build_ticket_refine_intent).
"""

from __future__ import annotations


def build_thread_session_intent(ticket, thread_uid: str) -> str:
    ac = "\n".join(f"- {c}" for c in (ticket.acceptance_criteria or [])) or "- (none yet)"
    return (
        "You are opening a planning conversation (a Thread) for the Ticket "
        "below. This is read-only against the repository — do not modify any "
        "code. Your job, in order:\n"
        "\n"
        f"Ticket uid: {ticket.uid}\n"
        f"Thread uid: {thread_uid}\n"
        f"Title: {ticket.title}\n"
        f"Priority: {ticket.priority}\n"
        "\n"
        "Current description:\n"
        f"{(ticket.description or '(not provided)').strip()}\n"
        "\n"
        "Current acceptance criteria:\n"
        f"{ac}\n"
        "\n"
        "Task:\n"
        "1. Study the code the ticket touches. Quote concrete file:line "
        "references.\n"
        "2. Interrogate the user: ask clarifying questions one question at a "
        "time, in plain language, and wait for each answer before asking the "
        "next. Surface trade-offs and your recommendation. Do NOT silently "
        "assume answers to open product questions.\n"
        f"3. Call `opensweep_platform_update_ticket` (ticket_uid `{ticket.uid}`) "
        "to sharpen title/description and set 2-6 independently testable "
        "acceptance criteria, reflecting what you learned.\n"
        "4. When the user is satisfied, write the implementation plan with "
        f"`opensweep_platform_submit_thread_plan` (thread_uid `{thread_uid}`, "
        "plan_markdown). The plan must list concrete steps, the files to "
        "touch, and a 'How to verify' section. Keep iterating on the plan in "
        "this conversation until the user approves or tells you to stop.\n"
        "Persist conclusions through the tools — a plan only in your reply "
        "does not count. Do not change the ticket's status; Gate 1 stays "
        "human-only."
    )


def build_implement_addendum(plan_text: str, decision_log: str) -> str:
    plan = (plan_text or "").strip()
    log = (decision_log or "").strip()
    if not plan and not log:
        return ""
    parts = ["\n\n# Context carried over from the planning thread\n"]
    if plan:
        parts.append(
            "Follow this plan; deviate only when the code contradicts it, and "
            "say so in your summary when you do.\n\n" + plan
        )
    if log:
        parts.append("\n\n" + log)
    return "".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd back_end && pytest tests/test_thread_intents.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add back_end/domains/threads/services/intents.py back_end/tests/test_thread_intents.py
git commit -m "feat: thread session + implement-addendum intent builders"
```

---

### Task 5: Platform tool `submit_thread_plan`

**Files:**
- Create: `back_end/domains/platform_tools/submit_thread_plan.py`
- Modify: `back_end/domains/platform_tools/__init__.py` (import + `__all__`, mirror `update_finding` entries at lines 26 and 32)
- Modify: `back_end/domains/platform_tools/dispatcher.py` (`_TOOLS` dict + import block)
- Modify: `back_end/api/v1/platform_tools.py` (HTTP route — mirror `http_update_finding` at lines 329-343)
- Modify: `back_end/tests/test_mcp_surface.py` (add `opensweep_platform_submit_thread_plan` to the writer-tool allow-list; run the test first to see the exact assertion set that fails)
- Test: `back_end/tests/test_thread_plan_tool.py`

**Interfaces:**
- Consumes: `Thread` (Task 1).
- Produces: `async def submit_thread_plan(*, thread_uid: str, plan_markdown: str, executor: str = "manual") -> dict` returning `{"thread_uid", "plan_state"}`; registered as dispatcher name `"submit_thread_plan"`, HTTP operation_id `opensweep_platform_submit_thread_plan`. Task 6's session intent (Task 4) already names it.

- [ ] **Step 1: Write the failing test**

```python
"""submit_thread_plan tool: registration + validation surface (pure)."""

import pytest
from fastapi import HTTPException

from domains.platform_tools.dispatcher import _TOOLS
from domains.platform_tools.submit_thread_plan import _validate


def test_tool_is_registered_in_dispatcher():
    assert "submit_thread_plan" in _TOOLS


def test_validation_rejects_empty_plan():
    with pytest.raises(HTTPException) as exc:
        _validate(thread_uid="th-1", plan_markdown="   ")
    assert exc.value.status_code == 422


def test_validation_rejects_missing_thread_uid():
    with pytest.raises(HTTPException):
        _validate(thread_uid="", plan_markdown="## Plan")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd back_end && pytest tests/test_thread_plan_tool.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the tool**

`back_end/domains/platform_tools/submit_thread_plan.py`:

```python
"""Platform tool: submit_thread_plan.

The thread session agent persists its implementation plan here. Sets the
thread's plan to `drafted` (idempotent re-submits allowed while the thread is
still refining) and records a timeline event. Approval stays human-only —
this tool can never set `approved`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from domains.threads.models import Thread
from infrastructure.audit import write_audit


def _validate(*, thread_uid: str, plan_markdown: str) -> None:
    if not (thread_uid or "").strip():
        raise HTTPException(status_code=422, detail="thread_uid is required")
    if not (plan_markdown or "").strip():
        raise HTTPException(status_code=422, detail="plan_markdown must not be empty")


async def submit_thread_plan(
    *,
    thread_uid: str,
    plan_markdown: str,
    executor: str = "manual",
) -> dict[str, Any]:
    _validate(thread_uid=thread_uid, plan_markdown=plan_markdown)
    thread = await Thread.nodes.get_or_none(uid=thread_uid)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    if thread.phase != "refining":
        raise HTTPException(
            status_code=409,
            detail=f"plan can only be drafted while refining — thread is '{thread.phase}'",
        )
    now = datetime.now(UTC)
    thread.plan_text = plan_markdown
    thread.plan_state = "drafted"
    thread.events = [
        *(thread.events or []),
        {"ts": now.isoformat(), "type": "plan_drafted", "by": executor},
    ]
    thread.updated_at = now
    await thread.save()
    await write_audit(
        kind="thread.plan_drafted",
        subject_uid=thread_uid,
        subject_type="Thread",
        actor_uid=executor,
        payload={"chars": len(plan_markdown)},
    )
    return {"thread_uid": thread_uid, "plan_state": "drafted"}
```

- [ ] **Step 4: Register in `__init__.py` and `dispatcher.py`**

In `back_end/domains/platform_tools/__init__.py`: add
`from domains.platform_tools.submit_thread_plan import submit_thread_plan` to the import block and `"submit_thread_plan"` to `__all__` (alphabetical position, next to the other `s` entries).

In `back_end/domains/platform_tools/dispatcher.py`: add `submit_thread_plan` to the `from domains.platform_tools import (...)` block and `"submit_thread_plan": submit_thread_plan,` to `_TOOLS`.

- [ ] **Step 5: Mount the HTTP route**

In `back_end/api/v1/platform_tools.py`, mirror the `http_update_finding` handler (lines 329-343) exactly — same dispatch helper, same auth dependency, new body model:

```python
class SubmitThreadPlanBody(BaseModel):
    plan_markdown: str = Field(min_length=1)


@router.post(
    "/submit-thread-plan/{thread_uid}",
    operation_id="opensweep_platform_submit_thread_plan",
)
async def http_submit_thread_plan(thread_uid: str, body: SubmitThreadPlanBody, ...):
    # copy the exact dependency signature + dispatch call pattern from
    # http_update_finding, passing name="submit_thread_plan",
    # fn=submit_thread_plan, thread_uid=thread_uid,
    # plan_markdown=body.plan_markdown
```

(The `...` above means: replicate `http_update_finding`'s parameter list and body verbatim — auth token dependency and executor attribution included. Do not invent a new pattern.)

- [ ] **Step 6: Run the tool test + MCP surface test; fix the allow-list**

Run: `cd back_end && pytest tests/test_thread_plan_tool.py tests/test_mcp_surface.py -v`
Expected: `test_thread_plan_tool` passes; `test_mcp_surface` may FAIL listing `opensweep_platform_submit_thread_plan` as an unknown writer — add it to the writer allow-list set in `tests/test_mcp_surface.py` (next to `opensweep_platform_submit_verdict`), then re-run: all pass.

- [ ] **Step 7: Commit**

```bash
git add back_end/domains/platform_tools back_end/api/v1/platform_tools.py back_end/tests/test_thread_plan_tool.py back_end/tests/test_mcp_surface.py
git commit -m "feat: submit_thread_plan platform tool"
```

---

### Task 6: ThreadService — create / get / list / plan ops + schemas

**Files:**
- Create: `back_end/domains/threads/schemas.py`
- Create: `back_end/domains/threads/services/thread_service.py`
- Test: `back_end/tests/test_thread_service_pure.py`

**Interfaces:**
- Consumes: `Thread`, `is_legal_phase_transition` (Task 1); `build_thread_session_intent` (Task 4); `trigger_run` from `domains.investigations.services.lifecycle` (existing, signature at `lifecycle.py:96-116`); `compose_playbook_intent` from `domains.agent_overlays.services.composition`; `ensure_policy_for_effort` from `domains.run_policies.services.effort`; `TicketService` (existing).
- Produces (used by Tasks 7-8 and the router in this task's follow-up):
  - `thread_to_dto(t: Thread) -> ThreadDTO`
  - `class ThreadService` with:
    - `async create(*, ticket_uid: str, actor_uid: str, org_uid: str) -> Thread` (dispatches the session run; 409 via `HTTPException` when an active thread exists for the ticket)
    - `async get_node(uid: str) -> Thread` (404 `HTTPException` when missing)
    - `async get_detail(uid: str) -> ThreadDetailDTO` (thread + run summaries)
    - `async list(*, repository_uid: str = "", subject_ticket_uid: str = "") -> list[Thread]`
    - `async update_plan(uid: str, plan_text: str, *, actor_uid: str) -> Thread` (hand-edit; approved plan drops back to `drafted`)
    - `async approve_plan(uid: str, *, actor_uid: str) -> Thread` (409 when `plan_text` empty)
    - `async transition(uid: str, to_phase: str, *, actor_uid: str) -> Thread` (matrix-checked, audited; also used by hooks)
    - `async record_event(thread: Thread, type: str, **payload) -> None`
    - `async attach_run(thread: Thread, run_uid: str) -> None` (appends to `run_uids`, sets `active_run_uid`, sets `Run.thread_uid`, records `run_attached` event)
  - Schemas: `ThreadDTO`, `ThreadDetailDTO` (adds `events: list[dict]`, `runs: list[ThreadRunSummaryDTO]`, `plan_text: str`), `ThreadRunSummaryDTO {uid, playbook, status, title, created_at}`, `CreateThreadRequest {ticket_uid}`, `UpdateThreadPlanRequest {plan_text}`.

`ThreadDTO` fields: `uid, repository_uid, subject_ticket_uid, phase, plan_state, branch, pr_uid, active_run_uid, created_by, created_at, updated_at` (pydantic `BaseModel`, mirror `domains/tickets/schemas.py` style).

- [ ] **Step 1: Write the failing test (pure parts)**

```python
"""ThreadService pure logic: DTO mapping + active-thread guard predicate."""

from types import SimpleNamespace

from domains.threads.services.thread_service import (
    has_active_thread,
    thread_to_dto,
)


def _thread(**over):
    base = dict(
        uid="th-1", repository_uid="r-1", subject_ticket_uid="t-1",
        phase="refining", plan_state="none", plan_text="", branch="",
        pr_uid="", active_run_uid="", run_uids=[], events=[],
        created_by="u-1", created_at=None, updated_at=None,
        plan_approved_by="", plan_approved_at=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_dto_mapping_roundtrip():
    dto = thread_to_dto(_thread())
    assert dto.uid == "th-1" and dto.phase == "refining"


def test_has_active_thread_true_for_non_terminal():
    assert has_active_thread([_thread(phase="refining")])
    assert has_active_thread([_thread(phase="in_review")])


def test_has_active_thread_false_for_terminal_only():
    assert not has_active_thread([_thread(phase="done"), _thread(phase="abandoned")])
    assert not has_active_thread([])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd back_end && pytest tests/test_thread_service_pure.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement schemas + service**

`back_end/domains/threads/schemas.py`:

```python
"""Thread DTOs (unified dev flow Phase 1)."""

from datetime import datetime

from pydantic import BaseModel, Field


class ThreadDTO(BaseModel):
    uid: str
    repository_uid: str
    subject_ticket_uid: str
    phase: str
    plan_state: str
    branch: str = ""
    pr_uid: str = ""
    active_run_uid: str = ""
    created_by: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ThreadRunSummaryDTO(BaseModel):
    uid: str
    playbook: str
    status: str
    title: str = ""
    created_at: datetime | None = None


class ThreadDetailDTO(ThreadDTO):
    plan_text: str = ""
    events: list[dict] = []
    runs: list[ThreadRunSummaryDTO] = []


class CreateThreadRequest(BaseModel):
    ticket_uid: str = Field(min_length=1)


class UpdateThreadPlanRequest(BaseModel):
    plan_text: str = Field(min_length=1)
```

`back_end/domains/threads/services/thread_service.py` (key shape — implement in full):

```python
"""ThreadService — orchestrates the refine→plan→implement conversation.

Threads reference Runs, never replace them. Phase moves only through
`transition` (matrix-checked + audited). One active (non-terminal) thread
per ticket.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException

from domains.threads.models import Thread, is_legal_phase_transition
from domains.threads.schemas import ThreadDetailDTO, ThreadDTO, ThreadRunSummaryDTO
from domains.threads.services.intents import build_thread_session_intent
from infrastructure.audit import write_audit
from logging_config import logger

TERMINAL_PHASES = {"done", "abandoned"}


def thread_to_dto(t) -> ThreadDTO:
    return ThreadDTO(
        uid=t.uid, repository_uid=t.repository_uid,
        subject_ticket_uid=t.subject_ticket_uid, phase=t.phase,
        plan_state=t.plan_state, branch=t.branch or "", pr_uid=t.pr_uid or "",
        active_run_uid=t.active_run_uid or "", created_by=t.created_by or "",
        created_at=t.created_at, updated_at=t.updated_at,
    )


def has_active_thread(threads: list) -> bool:
    return any(t.phase not in TERMINAL_PHASES for t in threads)


class ThreadService:
    async def get_node(self, uid: str) -> Thread:
        t = await Thread.nodes.get_or_none(uid=uid)
        if t is None:
            raise HTTPException(status_code=404, detail="not found")
        return t

    async def list(self, *, repository_uid: str = "", subject_ticket_uid: str = "") -> list[Thread]:
        qs = Thread.nodes
        if repository_uid:
            qs = qs.filter(repository_uid=repository_uid)
        if subject_ticket_uid:
            qs = qs.filter(subject_ticket_uid=subject_ticket_uid)
        return list(await qs.all())

    async def record_event(self, thread: Thread, type: str, **payload) -> None:
        now = datetime.now(UTC)
        thread.events = [*(thread.events or []), {"ts": now.isoformat(), "type": type, **payload}]
        thread.updated_at = now
        await thread.save()

    async def attach_run(self, thread: Thread, run_uid: str) -> None:
        from domains.investigations.models import Run

        thread.run_uids = [*(thread.run_uids or []), run_uid]
        thread.active_run_uid = run_uid
        await thread.save()
        run = await Run.nodes.get_or_none(uid=run_uid)
        if run is not None:
            run.thread_uid = thread.uid
            await run.save()
        await self.record_event(thread, "run_attached", run_uid=run_uid)

    async def create(self, *, ticket_uid: str, actor_uid: str, org_uid: str) -> Thread:
        # imports local to avoid cycles, mirroring api/v1/tickets.py
        from domains.agent_overlays.services.composition import compose_playbook_intent
        from domains.investigations.schemas import InvestigationEffort, RunTrigger
        from domains.investigations.services.lifecycle import LifecycleError, trigger_run
        from domains.run_policies.services.effort import ensure_policy_for_effort
        from domains.tickets.services.ticket_service import TicketService

        ticket = await TicketService().get_node(ticket_uid)
        existing = await self.list(subject_ticket_uid=ticket_uid)
        if has_active_thread(existing):
            raise HTTPException(status_code=409, detail="ticket already has an active thread")

        thread = Thread(
            uid=uuid4().hex,
            repository_uid=ticket.repository_uid,
            subject_ticket_uid=ticket_uid,
            created_by=actor_uid,
        )
        await thread.save()

        composed = await compose_playbook_intent(
            repository_uid=ticket.repository_uid,
            playbook="refine",
            stage="refine",
            repo_guidance="",
            custom_intent=build_thread_session_intent(ticket, thread.uid),
            org_uid=org_uid,
        )
        policy = await ensure_policy_for_effort(InvestigationEffort.NORMAL)
        try:
            run = await trigger_run(
                repository_uid=ticket.repository_uid,
                intent=composed.text,
                playbook="refine",
                title=f"Thread: {(ticket.title or 'ticket')[:80]}",
                target={"thread_uid": thread.uid, "ticket_uid": ticket_uid},
                linked_ticket_uid=ticket_uid,
                run_policy_uid=policy.uid,
                trigger=RunTrigger.MANUAL,
                triggered_by=actor_uid,
            )
        except LifecycleError as exc:
            await thread.delete()  # dispatch never started — no orphan threads
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await self.attach_run(thread, run.uid)
        await write_audit(
            kind="thread.created", subject_uid=thread.uid, subject_type="Thread",
            actor_uid=actor_uid, payload={"ticket_uid": ticket_uid, "run_uid": run.uid},
        )
        return thread

    async def get_detail(self, uid: str) -> ThreadDetailDTO:
        from domains.investigations.models import Run

        t = await self.get_node(uid)
        runs: list[ThreadRunSummaryDTO] = []
        for run_uid in t.run_uids or []:
            r = await Run.nodes.get_or_none(uid=run_uid)
            if r is not None:
                runs.append(ThreadRunSummaryDTO(
                    uid=r.uid, playbook=r.playbook, status=r.status,
                    title=r.title or "", created_at=r.created_at,
                ))
        base = thread_to_dto(t).model_dump()
        return ThreadDetailDTO(**base, plan_text=t.plan_text or "",
                               events=t.events or [], runs=runs)

    async def update_plan(self, uid: str, plan_text: str, *, actor_uid: str) -> Thread:
        t = await self.get_node(uid)
        if t.phase in TERMINAL_PHASES:
            raise HTTPException(status_code=409, detail=f"thread is {t.phase}")
        t.plan_text = plan_text
        t.plan_state = "drafted"  # hand-edits invalidate approval
        await t.save()
        await self.record_event(t, "plan_edited", by=actor_uid)
        await write_audit(kind="thread.plan_edited", subject_uid=uid,
                          subject_type="Thread", actor_uid=actor_uid, payload={})
        return t

    async def approve_plan(self, uid: str, *, actor_uid: str) -> Thread:
        t = await self.get_node(uid)
        if not (t.plan_text or "").strip():
            raise HTTPException(status_code=409, detail="no plan to approve")
        now = datetime.now(UTC)
        t.plan_state = "approved"
        t.plan_approved_by = actor_uid
        t.plan_approved_at = now
        await t.save()
        await self.record_event(t, "plan_approved", by=actor_uid)
        await write_audit(kind="thread.plan_approved", subject_uid=uid,
                          subject_type="Thread", actor_uid=actor_uid, payload={})
        return t

    async def transition(self, uid: str, to_phase: str, *, actor_uid: str) -> Thread:
        t = await self.get_node(uid)
        if not is_legal_phase_transition(t.phase, to_phase):
            raise HTTPException(status_code=409, detail=f"illegal transition {t.phase} → {to_phase}")
        frm = t.phase
        t.phase = to_phase
        await t.save()
        await self.record_event(t, "phase_changed", frm=frm, to=to_phase, by=actor_uid)
        await write_audit(kind="thread.phase_changed", subject_uid=uid,
                          subject_type="Thread", actor_uid=actor_uid,
                          payload={"from": frm, "to": to_phase})
        return t
```

- [ ] **Step 4: Run tests**

Run: `cd back_end && pytest tests/test_thread_service_pure.py tests/test_thread_transitions.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add back_end/domains/threads
git add back_end/tests/test_thread_service_pure.py
git commit -m "feat: ThreadService + schemas (create/plan/transition/timeline)"
```

---

### Task 7: Implement-from-thread (service method)

**Files:**
- Modify: `back_end/domains/threads/services/thread_service.py` (add `start_implement`)
- Test: `back_end/tests/test_thread_implement_addendum.py`

**Interfaces:**
- Consumes: `trigger_implement_run(ticket, *, triggered_by, trigger, intent_addendum)` (existing, `domains/delivery/services/implement_run_service.py:149-155`); `read_events(run_uid)` (existing, `domains/investigations/services/run_events.py:167`); `build_decision_log` (Task 3); `build_implement_addendum` (Task 4).
- Produces: `ThreadService.start_implement(uid: str, *, actor_uid: str) -> Run` — Task 9's router calls it. Pure helper `compose_addendum_for_thread(plan_state: str, plan_text: str, events: list[dict]) -> str` (exported for testing).

- [ ] **Step 1: Write the failing test**

```python
"""Implement carry-over: what gets injected into the implement run."""

from domains.threads.services.thread_service import compose_addendum_for_thread


def _ev(text):
    return {"seq": 1, "ts": "", "turn": 1, "type": "user_message", "text": text}


def test_approved_plan_is_carried():
    out = compose_addendum_for_thread("approved", "## Plan\n1. X", [_ev("soft gate")])
    assert "## Plan" in out and "soft gate" in out


def test_drafted_plan_is_also_carried():
    # Soft gate: an unapproved draft still beats no plan.
    out = compose_addendum_for_thread("drafted", "## Plan\n1. X", [])
    assert "## Plan" in out


def test_no_plan_no_conversation_gives_empty_addendum():
    assert compose_addendum_for_thread("none", "", []) == ""


def test_conversation_carried_even_without_plan():
    out = compose_addendum_for_thread("none", "", [_ev("use redis pub/sub")])
    assert "use redis pub/sub" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd back_end && pytest tests/test_thread_implement_addendum.py -v`
Expected: FAIL — `ImportError: cannot import name 'compose_addendum_for_thread'`

- [ ] **Step 3: Implement**

Add to `back_end/domains/threads/services/thread_service.py`:

```python
def compose_addendum_for_thread(plan_state: str, plan_text: str, events: list[dict]) -> str:
    from domains.threads.services.decision_log import build_decision_log
    from domains.threads.services.intents import build_implement_addendum

    plan = plan_text if plan_state in {"approved", "drafted"} else ""
    return build_implement_addendum(plan, build_decision_log(events))
```

And the service method (inside `ThreadService`):

```python
    async def start_implement(self, uid: str, *, actor_uid: str):
        from domains.delivery.services.implement_run_service import trigger_implement_run
        from domains.investigations.services.run_events import read_events
        from domains.tickets.services.ticket_service import TicketService

        t = await self.get_node(uid)
        if t.phase != "refining":
            raise HTTPException(status_code=409, detail=f"thread is {t.phase}, not refining")
        ticket = await TicketService().get_node(t.subject_ticket_uid)

        events: list[dict] = []
        if t.active_run_uid:
            try:
                events = read_events(t.active_run_uid)
            except Exception:  # noqa: BLE001 — carry-over is best-effort
                logger.warning(f"thread {uid}: could not read session events for carry-over",
                               extra={"tag": "threads"})
        addendum = compose_addendum_for_thread(t.plan_state, t.plan_text or "", events)

        # trigger_implement_run raises HTTPException(409) itself when Gate 1
        # hasn't passed or a PR already exists — let those propagate untouched.
        run = await trigger_implement_run(
            ticket, triggered_by=actor_uid, intent_addendum=addendum
        )
        await self.attach_run(t, run.uid)
        await self.transition(uid, "implementing", actor_uid=actor_uid)
        return run
```

- [ ] **Step 4: Run tests**

Run: `cd back_end && pytest tests/test_thread_implement_addendum.py tests/test_thread_service_pure.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add back_end/domains/threads/services/thread_service.py back_end/tests/test_thread_implement_addendum.py
git commit -m "feat: implement-from-thread with decision-log carry-over"
```

---

### Task 8: Lifecycle hooks — PR opened + PR merged advance the thread

**Files:**
- Create: `back_end/domains/threads/services/hooks.py`
- Modify: `back_end/domains/delivery/services/implement_run_service.py` (in `finalize_implement_run`, right after `run.linked_pr_uid = pr_uid` is saved, ~line 392-393)
- Modify: `back_end/api/v1/github_webhooks.py` (next to `mark_done_via_merge` call at ~line 466)
- Test: `back_end/tests/test_thread_hooks.py`

**Interfaces:**
- Consumes: `Run.thread_uid` (Task 2), `Thread.pr_uid` index (Task 1), `ThreadService.transition/record_event` (Task 6).
- Produces:
  - `async note_pr_opened_for_run(run) -> None` — never raises; no-op when `run.thread_uid` empty or transition illegal.
  - `async note_pr_merged(pr_uid: str) -> None` — never raises; advances every thread with this `pr_uid` from `in_review` to `done`.

- [ ] **Step 1: Write the failing test (pure guard logic)**

```python
"""Thread hooks are no-ops for standalone runs and never raise."""

import asyncio
from types import SimpleNamespace

from domains.threads.services.hooks import note_pr_opened_for_run


def test_noop_for_run_without_thread():
    run = SimpleNamespace(thread_uid="", linked_pr_uid="pr-1")
    # Must complete without touching the DB (no Thread lookup for "").
    asyncio.run(note_pr_opened_for_run(run))


def test_never_raises_on_lookup_failure(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("db down")

    import domains.threads.services.hooks as hooks
    monkeypatch.setattr(hooks, "_advance_to_in_review", boom)
    run = SimpleNamespace(uid="r-1", thread_uid="th-1", linked_pr_uid="pr-1")
    asyncio.run(note_pr_opened_for_run(run))  # no raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd back_end && pytest tests/test_thread_hooks.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement hooks**

`back_end/domains/threads/services/hooks.py`:

```python
"""Thread lifecycle hooks — called from delivery finalizers and webhooks.

Hook failures never corrupt the host flow (logged, not raised), mirroring
domains/investigations/services/playbooks.py.
"""

from __future__ import annotations

from logging_config import logger


async def _advance_to_in_review(run) -> None:
    from domains.delivery.models import PullRequest
    from domains.threads.services.thread_service import ThreadService

    svc = ThreadService()
    thread = await svc.get_node(run.thread_uid)
    if thread.phase != "implementing":
        return  # already advanced (idempotent) or user abandoned
    pr = await PullRequest.nodes.get_or_none(uid=run.linked_pr_uid)
    thread.pr_uid = run.linked_pr_uid or ""
    thread.branch = getattr(pr, "head_ref", "") or thread.branch
    await thread.save()
    await svc.transition(thread.uid, "in_review", actor_uid="system")
    await svc.record_event(thread, "pr_opened", pr_uid=thread.pr_uid)


async def note_pr_opened_for_run(run) -> None:
    """Implement finalizer hook: PR exists → thread moves to in_review."""
    if not (getattr(run, "thread_uid", "") or "") or not (run.linked_pr_uid or ""):
        return
    try:
        await _advance_to_in_review(run)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"thread hook pr_opened failed for run {run.uid}: {type(exc).__name__}: {exc}",
            extra={"tag": "threads"},
        )


async def note_pr_merged(pr_uid: str) -> None:
    """Merge webhook hook: every in_review thread on this PR → done."""
    if not (pr_uid or "").strip():
        return
    try:
        from domains.threads.models import Thread
        from domains.threads.services.thread_service import ThreadService

        svc = ThreadService()
        for thread in await Thread.nodes.filter(pr_uid=pr_uid).all():
            if thread.phase == "in_review":
                await svc.transition(thread.uid, "done", actor_uid="system")
                await svc.record_event(thread, "merged", pr_uid=pr_uid)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"thread hook pr_merged failed for PR {pr_uid}: {type(exc).__name__}: {exc}",
            extra={"tag": "threads"},
        )
```

Note: check the actual attribute name for the PR head branch on the
`PullRequest` model (`grep -n "head_ref\|head_branch" back_end/domains/delivery/models.py`)
and use that name instead of `head_ref` if it differs.

- [ ] **Step 4: Wire the call sites**

In `back_end/domains/delivery/services/implement_run_service.py`, in `finalize_implement_run`, immediately after the block that sets `run.linked_pr_uid = pr_uid` and saves the run (~lines 392-393):

```python
        from domains.threads.services.hooks import note_pr_opened_for_run

        await note_pr_opened_for_run(run)
```

In `back_end/api/v1/github_webhooks.py`, immediately after the `mark_done_via_merge` call (~line 466), inside the same merged-PR branch (the PR uid variable in scope there — read the surrounding function to pick the right variable name):

```python
                from domains.threads.services.hooks import note_pr_merged

                await note_pr_merged(pr.uid)
```

- [ ] **Step 5: Run tests**

Run: `cd back_end && pytest tests/test_thread_hooks.py tests/test_implement_run_intent.py -v`
Expected: all pass (existing implement tests unaffected)

- [ ] **Step 6: Commit**

```bash
git add back_end/domains/threads/services/hooks.py back_end/domains/delivery/services/implement_run_service.py back_end/api/v1/github_webhooks.py back_end/tests/test_thread_hooks.py
git commit -m "feat: thread hooks — PR opened/merged advance thread phase"
```

---

### Task 9: Thread API router

**Files:**
- Create: `back_end/api/v1/threads.py`
- Test: `back_end/tests/test_thread_routes.py`

**Interfaces:**
- Consumes: `ThreadService` (Tasks 6-7), schemas (Task 6), `require_role`, `get_current_user`, `require_repo_in_org` (existing, as in `api/v1/tickets.py`).
- Produces REST surface (auto-mounted by `app.py:_include_routers`, which scans `api/v1` modules for a module-level `router`):
  - `POST   /api/v1/threads` `{ticket_uid}` → `ThreadDTO` (maintainer+)
  - `GET    /api/v1/threads?repository_uid=&subject_ticket_uid=` → `list[ThreadDTO]`
  - `GET    /api/v1/threads/{uid}` → `ThreadDetailDTO`
  - `PATCH  /api/v1/threads/{uid}/plan` `{plan_text}` → `ThreadDTO` (maintainer+)
  - `POST   /api/v1/threads/{uid}/plan/approve` → `ThreadDTO` (maintainer+)
  - `POST   /api/v1/threads/{uid}/implement` → `{run_uid, thread_uid}` (maintainer+)
  - `POST   /api/v1/threads/{uid}/abandon` → `ThreadDTO` (maintainer+)

- [ ] **Step 1: Write the failing test (route-mount surface, mirror `tests/test_llm_provider_routes.py`)**

```python
"""Thread route surface is mounted with the expected paths + methods."""

from app import app


def test_thread_routes_are_mounted():
    paths = set(app.openapi().get("paths", {}).keys())
    assert "/api/v1/threads" in paths
    assert "/api/v1/threads/{uid}" in paths
    assert "/api/v1/threads/{uid}/plan" in paths
    assert "/api/v1/threads/{uid}/plan/approve" in paths
    assert "/api/v1/threads/{uid}/implement" in paths
    assert "/api/v1/threads/{uid}/abandon" in paths
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd back_end && pytest tests/test_thread_routes.py -v`
Expected: FAIL — paths missing

- [ ] **Step 3: Implement the router**

`back_end/api/v1/threads.py`:

```python
"""Thread routes — the unified dev flow's conversation-per-ticket surface.

Conversation I/O happens on the existing /runs endpoints (messages /
interrupt / ws) against the thread's active_run_uid; these routes own
lifecycle: create, plan gate, implement, abandon.
"""

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_current_user, require_role
from domains.tenancy import require_repo_in_org
from domains.threads.schemas import (
    CreateThreadRequest,
    ThreadDetailDTO,
    ThreadDTO,
    UpdateThreadPlanRequest,
)
from domains.threads.services.thread_service import ThreadService, thread_to_dto
from domains.users.schemas import UserDTO

router = APIRouter(prefix="/api/v1/threads", tags=["threads"])


@router.get("", response_model=list[ThreadDTO], operation_id="opensweep_thread_list")
async def list_threads(
    repository_uid: str | None = Query(None),
    subject_ticket_uid: str | None = Query(None),
    user: UserDTO = Depends(get_current_user),
):
    if repository_uid is not None:
        await require_repo_in_org(repository_uid, user.org_uid)
    threads = await ThreadService().list(
        repository_uid=repository_uid or "",
        subject_ticket_uid=subject_ticket_uid or "",
    )
    if repository_uid is None:
        from domains.tenancy import org_repo_uids

        allowed = await org_repo_uids(user.org_uid)
        threads = [t for t in threads if t.repository_uid in allowed]
    return [thread_to_dto(t) for t in threads]


@router.post("", response_model=ThreadDTO, operation_id="opensweep_thread_create")
async def create_thread(
    req: CreateThreadRequest, user: UserDTO = Depends(require_role("maintainer"))
):
    from domains.tickets.services.ticket_service import TicketService

    ticket = await TicketService().get_node(req.ticket_uid)
    await require_repo_in_org(ticket.repository_uid, user.org_uid)
    t = await ThreadService().create(
        ticket_uid=req.ticket_uid, actor_uid=user.uid, org_uid=user.org_uid
    )
    return thread_to_dto(t)


@router.get("/{uid}", response_model=ThreadDetailDTO, operation_id="opensweep_thread_get")
async def get_thread(uid: str, user: UserDTO = Depends(get_current_user)):
    svc = ThreadService()
    t = await svc.get_node(uid)
    await require_repo_in_org(t.repository_uid, user.org_uid)
    return await svc.get_detail(uid)


@router.patch("/{uid}/plan", response_model=ThreadDTO, operation_id="opensweep_thread_update_plan")
async def update_plan(
    uid: str, req: UpdateThreadPlanRequest, user: UserDTO = Depends(require_role("maintainer"))
):
    svc = ThreadService()
    t = await svc.get_node(uid)
    await require_repo_in_org(t.repository_uid, user.org_uid)
    t = await svc.update_plan(uid, req.plan_text, actor_uid=user.uid)
    return thread_to_dto(t)


@router.post(
    "/{uid}/plan/approve", response_model=ThreadDTO, operation_id="opensweep_thread_approve_plan"
)
async def approve_plan(uid: str, user: UserDTO = Depends(require_role("maintainer"))):
    svc = ThreadService()
    t = await svc.get_node(uid)
    await require_repo_in_org(t.repository_uid, user.org_uid)
    t = await svc.approve_plan(uid, actor_uid=user.uid)
    return thread_to_dto(t)


@router.post("/{uid}/implement", operation_id="opensweep_thread_implement")
async def implement_thread(uid: str, user: UserDTO = Depends(require_role("maintainer"))) -> dict:
    svc = ThreadService()
    t = await svc.get_node(uid)
    await require_repo_in_org(t.repository_uid, user.org_uid)
    run = await svc.start_implement(uid, actor_uid=user.uid)
    return {"run_uid": run.uid, "thread_uid": uid}


@router.post("/{uid}/abandon", response_model=ThreadDTO, operation_id="opensweep_thread_abandon")
async def abandon_thread(uid: str, user: UserDTO = Depends(require_role("maintainer"))):
    svc = ThreadService()
    t = await svc.get_node(uid)
    await require_repo_in_org(t.repository_uid, user.org_uid)
    t = await svc.transition(uid, "abandoned", actor_uid=user.uid)
    return thread_to_dto(t)
```

- [ ] **Step 4: Run tests + full suite**

Run: `cd back_end && pytest tests/test_thread_routes.py -v && pytest -q`
Expected: routes test passes; full suite green (DB-gated tests skip as usual)

- [ ] **Step 5: Commit**

```bash
git add back_end/api/v1/threads.py back_end/tests/test_thread_routes.py
git commit -m "feat: thread REST API"
```

---

### Task 10: Frontend types + threadStore

**Files:**
- Modify: `front_end/src/types/api.ts` (append thread types next to the ticket types)
- Create: `front_end/src/stores/threadStore.ts`

**Interfaces:**
- Consumes: `apiGet/apiPost/apiPatch` from `@/services/api` (existing).
- Produces (Tasks 11-12 import these): types `ThreadPhase`, `PlanState`, `ThreadDTO`, `ThreadRunSummaryDTO`, `ThreadDetailDTO`, `ThreadEventDTO`; store `useThreadStore` with `createThread(ticketUid)`, `getThread(uid)`, `listThreads(filters)`, `updatePlan(uid, planText)`, `approvePlan(uid)`, `implement(uid)`, `abandon(uid)`.

- [ ] **Step 1: Add types to `front_end/src/types/api.ts`**

```typescript
// ── Threads (unified dev flow) ────────────────────────────────────────────

export type ThreadPhase = 'refining' | 'implementing' | 'in_review' | 'done' | 'abandoned'
export type PlanState = 'none' | 'drafted' | 'approved'

export interface ThreadDTO {
  uid: string
  repository_uid: string
  subject_ticket_uid: string
  phase: ThreadPhase
  plan_state: PlanState
  branch: string
  pr_uid: string
  active_run_uid: string
  created_by: string
  created_at: string | null
  updated_at: string | null
}

export interface ThreadRunSummaryDTO {
  uid: string
  playbook: string
  status: string
  title: string
  created_at: string | null
}

export interface ThreadEventDTO {
  ts: string
  type: string
  [key: string]: unknown
}

export interface ThreadDetailDTO extends ThreadDTO {
  plan_text: string
  events: ThreadEventDTO[]
  runs: ThreadRunSummaryDTO[]
}
```

- [ ] **Step 2: Create the store**

`front_end/src/stores/threadStore.ts`:

```typescript
import { defineStore } from 'pinia'
import { apiGet, apiPatch, apiPost } from '@/services/api'
import type { ThreadDTO, ThreadDetailDTO } from '@/types/api'

export const useThreadStore = defineStore('threads', () => {
  async function createThread(ticketUid: string): Promise<ThreadDTO> {
    return apiPost<ThreadDTO>('/threads', { ticket_uid: ticketUid })
  }

  async function getThread(uid: string): Promise<ThreadDetailDTO> {
    return apiGet<ThreadDetailDTO>(`/threads/${uid}`)
  }

  async function listThreads(opts: {
    repository_uid?: string
    subject_ticket_uid?: string
  } = {}): Promise<ThreadDTO[]> {
    const qs = new URLSearchParams()
    Object.entries(opts).forEach(([k, v]) => {
      if (v) qs.set(k, String(v))
    })
    const url = qs.toString() ? `/threads?${qs.toString()}` : '/threads'
    return apiGet<ThreadDTO[]>(url)
  }

  async function updatePlan(uid: string, planText: string): Promise<ThreadDTO> {
    return apiPatch<ThreadDTO>(`/threads/${uid}/plan`, { plan_text: planText })
  }

  async function approvePlan(uid: string): Promise<ThreadDTO> {
    return apiPost<ThreadDTO>(`/threads/${uid}/plan/approve`, {})
  }

  async function implement(uid: string): Promise<{ run_uid: string; thread_uid: string }> {
    return apiPost<{ run_uid: string; thread_uid: string }>(`/threads/${uid}/implement`, {})
  }

  async function abandon(uid: string): Promise<ThreadDTO> {
    return apiPost<ThreadDTO>(`/threads/${uid}/abandon`, {})
  }

  return { createThread, getThread, listThreads, updatePlan, approvePlan, implement, abandon }
})
```

(If `apiPatch` does not exist in `@/services/api`, check the exports — `stores/ticketStore.ts:3` imports `apiPatch`, so it does.)

- [ ] **Step 3: Verify**

Run: `cd front_end && npm run type-check`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add front_end/src/types/api.ts front_end/src/stores/threadStore.ts
git commit -m "feat: thread types + Pinia store"
```

---

### Task 11: TestLocallyButton component

**Files:**
- Create: `front_end/src/components/delivery/TestLocallyButton.vue`

**Interfaces:**
- Consumes: `Button` from `@/components/ui/button`, `useToast` from `@/composables/useToast`.
- Produces: `<TestLocallyButton :branch="..." :pr-number="..." />` — Task 12 mounts it in ThreadView; also mount it in `PullRequestDetailView.vue` next to the existing PR actions.

- [ ] **Step 1: Implement**

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { Copy } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { useToast } from '@/composables/useToast'

const props = defineProps<{
  branch?: string
  prNumber?: number | null
}>()

const toast = useToast()

const command = computed(() => {
  if (props.prNumber) return `gh pr checkout ${props.prNumber}`
  if (props.branch)
    return `git fetch origin ${props.branch} && git worktree add ../$(basename $(git rev-parse --show-toplevel))--${props.branch.replace(/\//g, '-')} ${props.branch}`
  return ''
})

async function copy() {
  if (!command.value) return
  await navigator.clipboard.writeText(command.value)
  toast.success('Checkout command copied — paste it in your terminal')
}
</script>

<template>
  <Button v-if="command" variant="outline" size="sm" @click="copy">
    <Copy class="mr-1.5 h-3.5 w-3.5" />
    Test locally
  </Button>
</template>
```

Note: confirm the toast API (`toast.success(...)`) against an existing caller
(`grep -rn "useToast()" front_end/src/views/AskView.vue`) and match it.

- [ ] **Step 2: Mount in PR detail view**

In `front_end/src/views/PullRequestDetailView.vue`, import the component and render it in the header/actions area, passing the PR's branch and GitHub number from the already-loaded PR DTO (field names: check `PullRequestDTO` in `front_end/src/types/api.ts` — expected `head_ref`/`github_number`-style fields; use the actual names).

- [ ] **Step 3: Verify**

Run: `cd front_end && npm run type-check && npm run build`
Expected: clean

- [ ] **Step 4: Commit**

```bash
git add front_end/src/components/delivery/TestLocallyButton.vue front_end/src/views/PullRequestDetailView.vue
git commit -m "feat: Test locally button (gh pr checkout / worktree command)"
```

---

### Task 12: ThreadView — chat + plan rail + timeline + route

**Files:**
- Create: `front_end/src/views/ThreadView.vue`
- Create: `front_end/src/components/threads/PlanPanel.vue`
- Create: `front_end/src/components/threads/ThreadTimeline.vue`
- Modify: `front_end/src/router/index.ts` (global detail route next to `tickets/:uid` at line ~70)

**Interfaces:**
- Consumes: `useThreadStore` (Task 10), `RunTranscript` (`@/components/runs/RunTranscript.vue`, props `{events, live?, streamingText?}`), `useRunSocket` (`@/composables/useRunSocket.ts`), `TestLocallyButton` (Task 11), `MarkdownView` (`@/components/ui/markdown/MarkdownView.vue`), ui `Button/Card/Badge/Textarea`.
- Produces: route `{ path: 'threads/:uid', name: 'thread-detail' }`.

- [ ] **Step 1: Router entry**

In `front_end/src/router/index.ts`, next to the `tickets/:uid` route (line ~70):

```typescript
        { path: 'threads/:uid', name: 'thread-detail', component: () => import('@/views/ThreadView.vue') },
```

Copy whatever `meta`/guard options the sibling `ticket-detail` route carries.

- [ ] **Step 2: PlanPanel**

`front_end/src/components/threads/PlanPanel.vue`:

```vue
<script setup lang="ts">
import { ref, watch } from 'vue'
import { Check, Pencil } from 'lucide-vue-next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import MarkdownView from '@/components/ui/markdown/MarkdownView.vue'
import type { PlanState } from '@/types/api'

const props = defineProps<{
  planText: string
  planState: PlanState
  editable: boolean
}>()
const emit = defineEmits<{
  (e: 'save', text: string): void
  (e: 'approve'): void
}>()

const editing = ref(false)
const draft = ref(props.planText)
watch(() => props.planText, (v) => { if (!editing.value) draft.value = v })

function save() {
  editing.value = false
  if (draft.value !== props.planText) emit('save', draft.value)
}
</script>

<template>
  <Card>
    <CardContent class="space-y-3 p-4">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-semibold">Plan</h3>
        <div class="flex items-center gap-2">
          <Badge :variant="planState === 'approved' ? 'default' : 'secondary'">
            {{ planState }}
          </Badge>
          <Button v-if="editable && !editing" variant="ghost" size="sm" @click="editing = true">
            <Pencil class="h-3.5 w-3.5" />
          </Button>
          <Button
            v-if="editable && planState === 'drafted' && !editing"
            size="sm"
            @click="emit('approve')"
          >
            <Check class="mr-1 h-3.5 w-3.5" /> Approve
          </Button>
        </div>
      </div>
      <template v-if="editing">
        <textarea
          v-model="draft"
          class="min-h-64 w-full rounded-md border bg-transparent p-2 font-mono text-xs"
        />
        <div class="flex gap-2">
          <Button size="sm" @click="save">Save</Button>
          <Button size="sm" variant="ghost" @click="editing = false">Cancel</Button>
        </div>
      </template>
      <MarkdownView v-else-if="planText" :source="planText" />
      <p v-else class="text-sm text-muted-foreground">
        No plan yet — the agent drafts one in the conversation, or say “just implement it”.
      </p>
    </CardContent>
  </Card>
</template>
```

Note: check `MarkdownView`'s prop name (`source` vs `content`) at
`front_end/src/components/ui/markdown/MarkdownView.vue` and match it.

- [ ] **Step 3: ThreadTimeline**

`front_end/src/components/threads/ThreadTimeline.vue`:

```vue
<script setup lang="ts">
import { computed } from 'vue'
import type { ThreadEventDTO, ThreadRunSummaryDTO } from '@/types/api'

const props = defineProps<{
  events: ThreadEventDTO[]
  runs: ThreadRunSummaryDTO[]
}>()

const LABELS: Record<string, string> = {
  run_attached: 'Agent session started',
  plan_drafted: 'Plan drafted',
  plan_edited: 'Plan edited by hand',
  plan_approved: 'Plan approved',
  phase_changed: 'Phase changed',
  pr_opened: 'Draft PR opened',
  merged: 'PR merged — thread done',
}

const items = computed(() =>
  [...props.events].reverse().map((e) => ({
    ts: e.ts,
    label:
      e.type === 'phase_changed'
        ? `Phase: ${String(e.frm)} → ${String(e.to)}`
        : (LABELS[e.type] ?? e.type),
  }))
)
</script>

<template>
  <div class="space-y-1.5">
    <h3 class="text-sm font-semibold">Timeline</h3>
    <ol class="space-y-1 text-xs text-muted-foreground">
      <li v-for="(item, i) in items" :key="i" class="flex justify-between gap-2">
        <span>{{ item.label }}</span>
        <span class="tabular-nums">{{ new Date(item.ts).toLocaleTimeString() }}</span>
      </li>
    </ol>
  </div>
</template>
```

- [ ] **Step 4: ThreadView**

`front_end/src/views/ThreadView.vue` — the load-bearing wiring. **Open `front_end/src/views/RunDetailView.vue` first and mirror its `useRunSocket` usage exactly** (connect args, event accumulation, message send, interrupt) — the sketch below shows structure and store calls; the socket lines must match the composable's real exports (type-check enforces this):

```vue
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import RunTranscript from '@/components/runs/RunTranscript.vue'
import PlanPanel from '@/components/threads/PlanPanel.vue'
import ThreadTimeline from '@/components/threads/ThreadTimeline.vue'
import TestLocallyButton from '@/components/delivery/TestLocallyButton.vue'
import { useThreadStore } from '@/stores/threadStore'
import { useToast } from '@/composables/useToast'
import { useRunSocket } from '@/composables/useRunSocket'
import type { ThreadDetailDTO } from '@/types/api'

const route = useRoute()
const router = useRouter()
const threads = useThreadStore()
const toast = useToast()

const uid = computed(() => String(route.params.uid))
const thread = ref<ThreadDetailDTO | null>(null)

// ── Conversation: same transport as RunDetailView, against active_run_uid ──
// Mirror RunDetailView.vue's socket wiring verbatim: connect on mount with
// thread.value.active_run_uid, accumulate events for <RunTranscript>, expose
// sendMessage(text) + interrupt(). Reconnect when active_run_uid changes
// (implement dispatch swaps the run).

async function reload() {
  thread.value = await threads.getThread(uid.value)
}

onMounted(reload)

async function onSavePlan(text: string) {
  await threads.updatePlan(uid.value, text)
  await reload()
}

async function onApprovePlan() {
  await threads.approvePlan(uid.value)
  toast.success('Plan approved')
  await reload()
}

async function onImplement() {
  try {
    await threads.implement(uid.value)
    toast.success('Implementation started')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Could not start implementation')
  }
  await reload()
}

async function onAbandon() {
  await threads.abandon(uid.value)
  await reload()
}

const prNumber = computed(() => null) // wire from PR detail via pr_uid when present
</script>

<template>
  <div v-if="thread" class="flex h-full gap-4 p-4">
    <!-- Chat pane -->
    <section class="flex min-w-0 flex-1 flex-col">
      <header class="mb-2 flex items-center gap-2">
        <h1 class="truncate text-lg font-semibold">Thread</h1>
        <Badge>{{ thread.phase }}</Badge>
        <div class="ml-auto flex gap-2">
          <Button
            v-if="thread.phase === 'refining'"
            size="sm"
            @click="onImplement"
          >Implement</Button>
          <TestLocallyButton
            v-if="thread.branch"
            :branch="thread.branch"
            :pr-number="prNumber"
          />
          <Button
            v-if="thread.phase !== 'done' && thread.phase !== 'abandoned'"
            size="sm"
            variant="ghost"
            @click="onAbandon"
          >Abandon</Button>
        </div>
      </header>
      <!-- RunTranscript + input bar: mirror RunDetailView's template here -->
    </section>

    <!-- Right rail -->
    <aside class="w-96 shrink-0 space-y-4 overflow-y-auto">
      <PlanPanel
        :plan-text="thread.plan_text"
        :plan-state="thread.plan_state"
        :editable="thread.phase === 'refining'"
        @save="onSavePlan"
        @approve="onApprovePlan"
      />
      <ThreadTimeline :events="thread.events" :runs="thread.runs" />
      <RouterLink
        v-if="thread.pr_uid"
        :to="{ name: 'pull-request-detail', params: { uid: thread.pr_uid } }"
        class="block text-sm text-primary underline"
      >View pull request →</RouterLink>
    </aside>
  </div>
</template>
```

The two `<!-- mirror RunDetailView -->` blocks are the only parts left open on
purpose: they must be copied from `RunDetailView.vue`'s working socket +
transcript + input implementation (it already handles replay, deltas,
interrupt, REST fallback). Copy, then adapt the run uid source to
`thread.active_run_uid`.

- [ ] **Step 5: Verify**

Run: `cd front_end && npm run type-check && npm run build`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add front_end/src/views/ThreadView.vue front_end/src/components/threads front_end/src/router/index.ts
git commit -m "feat: ThreadView with chat pane, plan rail, and timeline"
```

---

### Task 13: Ticket entry point + final verification

**Files:**
- Modify: `front_end/src/views/TicketDetailView.vue` (actions area)
- Modify: `front_end/src/components/tickets/TicketCard.vue` (phase chip, optional — skip if the card is crowded)

**Interfaces:**
- Consumes: `useThreadStore.createThread/listThreads` (Task 10), router `thread-detail` (Task 12).
- Produces: "Start thread" / "Open thread" button on ticket detail.

- [ ] **Step 1: Add the button**

In `TicketDetailView.vue`, next to the existing `TicketRefineButton`/`TicketImplementButton` components:

```typescript
import { useThreadStore } from '@/stores/threadStore'

const threadStore = useThreadStore()
const activeThreadUid = ref<string | null>(null)

onMounted(async () => {
  const existing = await threadStore.listThreads({ subject_ticket_uid: ticketUid })
  activeThreadUid.value =
    existing.find((t) => t.phase !== 'done' && t.phase !== 'abandoned')?.uid ?? null
})

async function startThread() {
  const t = activeThreadUid.value
    ? { uid: activeThreadUid.value }
    : await threadStore.createThread(ticketUid)
  router.push({ name: 'thread-detail', params: { uid: t.uid } })
}
```

```vue
<Button size="sm" @click="startThread">
  {{ activeThreadUid ? 'Open thread' : 'Start thread' }}
</Button>
```

(Adapt variable names to the view's existing script — it already has the
ticket uid and a router instance; reuse those.)

- [ ] **Step 2: Full verification**

Run:
```bash
cd back_end && pytest -q
cd ../front_end && npm run type-check && npm run build
```
Expected: backend suite green (DB-gated tests skip), type-check + build clean.

- [ ] **Step 3: Commit**

```bash
git add front_end/src/views/TicketDetailView.vue front_end/src/components/tickets/TicketCard.vue
git commit -m "feat: start/open thread from ticket detail"
```

---

## Deferred to later phases (explicitly NOT in this plan)

- **CLI session resume** (`cli_session_id` handoff from refine session to
  implement run): the spec's "resume when possible" half. Phase 1 ships the
  "carry-over always" half (decision log + plan addendum), which the spec
  guarantees as the baseline. Resume needs executor/workspace cooperation and
  belongs with the Phase 2/3 run-infrastructure work.
- Narration sidecar + expandable feed (Phase 2)
- Verdict/finding cards in the thread, discuss-a-finding, fix-from-thread (Phase 3)
- Test recipes, ticket test artifacts DoD, `opensweep connect` user-scoped MCP (Phase 4)
- Group flows: thread on parent → one branch/PR closing subtickets (Phase 5)
- Preview environments (separate spec)
