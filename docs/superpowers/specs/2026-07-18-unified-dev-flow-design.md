# Unified Dev Flow ("Threads") — Design

**Date:** 2026-07-18
**Status:** Approved design; **Revision 2 (same day): the flow model was
superseded after dogfooding — see "Revision 2" below.** Original text kept
for the record.
**Scope:** opensweep (public repo). No cloud-overlay changes required; extension points only if billing/entitlements need to meter threads later.

## Revision 2 — one thread agent, phase-gated by the platform

Dogfooding the v1 build surfaced a fault line in Decision 2 ("one continuous
conversation" realized as SEPARATE runs stitched together): the planning
agent had to be prompt-forbidden from implementing, and the implement run was
a different, cold agent fed a summary. The conversation identity broke at
exactly the moment work started, and prompt-level enforcement of the split
proved brittle (the planning agent implemented into its throwaway clone).

**Key insight:** the write gate is platform-side — agents never push;
the platform validates and pushes after the fact. So the read-only-planning
vs write-implementation *sandbox* split was never load-bearing. The phase
gate belongs in the platform, not in the prompt.

**Superseding model:** a new `thread` playbook. ONE run, ONE conversation,
in a write sandbox (work branch created up front) for the whole lifecycle:

- **refining:** the agent explores, interrogates the user (`ask_user`),
  sharpens the ticket, submits the plan (`submit_thread_plan`). The
  finalizer runs no write gate — nothing the agent does in the sandbox
  goes anywhere.
- **Approval = a platform-authored message, not a new run.** "Implement"
  checks Gate 1 (ticket todo/in-progress), flips the thread to
  `implementing`, and sends a structured go-message into the SAME
  conversation. Same agent, full memory; the decision-log carry-over
  machinery is deleted as unnecessary.
- **implementing / in_review:** each completed turn runs the existing
  validate → push → draft-PR machinery (implement-style first, fix-style
  continuation after). Review verdicts arrive as message turns; fixes are
  further turns of the same conversation. For thread-owned PRs the
  auto-fix chain messages the thread run instead of dispatching a fix run.
- **Review stays an independent cold run** — unchanged; that separation is
  the one that earns its keep.
- The thread agent may use its executor's native subagents for parallel
  exploration; platform-spawned independent runs (review, verify) act as
  platform-managed subagents whose outputs land on the thread timeline.

Consequences: transcript stitching becomes a legacy-only path (one run =
one transcript), `decision_log` carry-over is removed, and legacy v1
threads (separate-run model) remain viewable, with implement falling back
to the old dispatch for them.

## Problem

The delivery pipeline (refine → implement → review → fix → merge) works, but each
step is a separate run with a fresh agent and its own transcript. Working a
ticket end-to-end from the UI feels like talking to strangers:

- No interactive planning mode: `refine` drafts a plan, but the agent never
  grills the user with questions, and there is no plan-approval moment.
- One-shot implementation is brittle; steering exists at the API level
  (messages, interrupt) but there is no single place to follow and steer a
  piece of work across phases.
- Progress visibility is a raw event transcript (tool calls, diffs), not
  explainable language.
- Testing an agent's branch is unsupported: sandboxes are platform-side and
  disposable, and a bare `git checkout` gives you code without a working
  environment (services, migrations, seed data).

Goal: the OpenSweep UI becomes the primary driving seat for the whole flow,
matching the ergonomics of a local Claude Code session.

## Decisions (from brainstorming)

1. **Driving seat:** OpenSweep UI, end-to-end.
2. **Flow model (synthesis):** one continuous conversation for
   refine → plan → implement (+ fixes); review runs stay independent and
   cold-context by design, their output feeds back into the conversation.
3. **Plan gate:** soft — the thread always offers planning; the user may
   approve a plan or say "just implement" per ticket.
4. **Explainability:** plain-language narration feed as the primary view, each
   line expandable to the underlying raw events.
5. **Branch testing:** one-click local checkout + local-agent-assisted
   environment setup via MCP now; platform preview environments later
   (separate spec).
6. **Groups:** one thread, one branch, one PR for a ticket group (parent +
   subtickets); merging closes all members.
7. **Architecture:** new first-class `Thread` entity (Option 1). Runs,
   sandboxes, policies, and convergence machinery stay unchanged.

## Design

### Thread entity

New `threads` domain. A **Thread** = "one piece of work moving through the
pipeline, with one conversation attached."

- **Subject:** exactly one ticket or one group-parent ticket
  (one active thread per subject).
- **Fields:** `uid`, `repository_uid`, `subject_ticket_uid`, `phase`,
  `plan_state`, `branch`, `pr_uid`, `created_by`, timestamps.
- **Phases:** `refining → implementing → in_review → done` with an explicit
  transition matrix enforced server-side (same style as ticket transitions,
  cf. `back_end/tests/test_ticket_transitions.py`). Terminal: `done`,
  `abandoned`.
- **Plan:** artifact attached to the thread (and mirrored to the ticket as
  today), `plan_state ∈ {none, drafted, approved}`. Approval records
  who/when. Approval is NOT required to enter `implementing` (soft gate),
  but an approved plan is injected into the implement run's context.
- **Timeline:** ordered entries referencing spawned run uids plus thread
  events (phase change, plan drafted/approved, PR opened, verdict received,
  fix round started, run failed/retried).

API surface (`/api/v1/threads`): create from ticket, get with timeline,
approve/edit plan, trigger implement, abandon. Conversation I/O reuses the
existing run endpoints (`/runs/{uid}/messages`, `/interrupt`, `/ws`)
unchanged — the thread resolves "which run is currently the conversation."

### Lifecycle

1. **Start thread** (from ticket detail or group parent): creates the Thread
   and dispatches an interactive session — read-only sandbox like Ask, but
   with the refine playbook's ticket-mutation tools and a prompt that
   instructs the agent to interrogate the user (clarifying questions, one at
   a time), update the ticket, and draft a plan artifact. This is plan mode.
2. **Plan gate (soft):** user approves the plan (one click or message),
   edits it by hand (it is an editable artifact), iterates via chat, or
   skips planning entirely.
3. **Implement:** dispatched from within the thread. Write sandbox, work
   branch per existing implement-run mechanics. Phase → `implementing`.
   The user steers through the same chat surface (existing message /
   interrupt / cancel APIs).
4. **PR opened** → phase `in_review`. Independent review runs attach to the
   timeline; verdicts and findings render inline. Fix work continues the
   user's conversation (implementer fixes; reviewer stays cold). Convergence
   status renders live in the thread header.
5. **User merges** → thread `done`. Group threads close all member tickets.

### Conversation continuity: resume when possible, carry-over always

Ideal: the implement run resumes the refine session via `cli_session_id`
(executor session resume). This cannot be guaranteed across the
read-only → write sandbox boundary (CLI session state lives with the
workspace). Therefore:

- **Always:** at the refine→implement transition the platform distills the
  thread conversation into a structured **decision log** (questions asked,
  answers given, constraints discovered, rejected alternatives) and injects
  it plus the plan into the implement run's opening context.
- **When feasible** (same workspace host, executor supports it, session file
  present): additionally resume the CLI session.

The UI shows one unbroken conversation either way. The same mechanism covers
run replacement after failure (see Error handling).

### Narration layer

A **sidecar summarizer** — never the coding agent itself — produces the
plain-language feed:

- A watcher subscribes to the existing per-run event stream
  (`run_events:{uid}` Redis doorbell + `events.jsonl` replay by offset).
- It batches durable events and asks a cheap/fast model on the active
  provider for one-line narration events ("Reading the auth middleware to
  understand token validation", "Tests failed on `test_refresh_expiry` —
  adjusting the fix").
- Each narration event records the `seq` range of raw events it covers;
  narration events are appended to the same events file/stream with their
  own type, so transports (WS/REST replay) need no changes.
- Executor-agnostic (reads normalized events, not executor output). The
  coding agent's prompt and token budget are untouched.
- **Fallback:** if no model is available/configured, template narration from
  event shape ("Editing `auth/service.py`", "Running `pytest`").

### Review feedback in the thread

Review runs are unchanged (independent, SHA-bound, cold context,
`analyze_only`). New behavior is presentational + routing:

- Verdicts and findings for the thread's PR become timeline cards in the
  conversation.
- From a card: expand the finding, jump to the diff, **discuss** (message
  goes to the user's implementer session with the finding attached as
  context), or trigger a fix round.
- User instructions in the thread reach fix runs the same way human PR
  comments already outrank agent judgment in the review service.
- Convergence predicate (CI, fresh verdict, clean round, ledger) renders
  live at the top of the thread.

### Testing the branch (three layers + MCP connect)

**Principle: don't make the platform understand every stack — give a local
agent the knowledge to set it up.**

1. **Test Recipe (living doc, per repo):** canonical agent-maintained doc:
   services to start, migration command, seed command, run command,
   healthcheck, reset procedure, and an **isolation convention** — a test
   profile with separate compose project name/volumes/ports
   (`docker compose -p <repo>-test`; reset = `down -v`) so testing a branch
   with new migrations never touches the developer's main dev database.
   Kept fresh by discovery sweeps (existing freshness stamps). Implement
   agents must update it when they change setup/migrations (definition of
   done). The same recipe later powers platform preview environments.
2. **Ticket-scoped test artifacts:** the plan template gains a "how to
   verify" section. The implement agent must deliver on the branch: a test
   note on the thread/PR (steps, what to click, expected behavior) and,
   when the change needs data to be meaningfully testable, committed seed
   fixtures (e.g., additions to the repo's seed script) plus migration
   reset notes.
3. **`opensweep connect` (user-scoped MCP):** OpenSweep exposes an MCP
   endpoint authenticated by a personal, role-scoped token (distinct from
   per-run `osrt_` tokens) surfacing a curated platform-tool subset: read
   tickets/plans/docs/memories/test recipes/threads; write thread comments
   and ticket updates per role. The UI provides one-click config snippets
   for Claude Code (`claude mcp add`), Codex, and OpenCode. A local agent
   can then take "set up ticket #42 for testing": pull ticket + test note +
   recipe over MCP, `gh pr checkout` / fetch the branch, bring up the test
   profile, run migrations, seed data, walk the user through verification,
   and report results back to the thread.
4. **Manual escape hatch:** a "Test locally" button on thread/PR copies a
   ready-made `gh pr checkout <num>` (or
   `git fetch origin <branch> && git worktree add …`) command.

Platform preview environments (boot the branch in a container behind a
per-thread URL) are explicitly **out of scope** — follow-up spec; the test
recipe is designed to be its config source.

### Frontend

One new **Thread view**:

- Left: chat pane — narration feed by default, raw-transcript toggle,
  per-line expand to underlying events, status-aware input bar unifying
  send/interrupt/cancel across phases.
- Right rail: plan (editable, approve control), run timeline, live
  convergence status, "Test locally" button, MCP connect hint.
- Entry points: "Start thread" on ticket detail and group parents; thread
  phase indicator on the Tickets board.
- Existing Ask/run/PR views remain; the thread is a lens over them.

### Error handling

- A thread never dies with its run. Run failure / timeout / cost ceiling
  surfaces as a plain-language timeline event with retry/resume actions that
  attach a fresh run to the thread, decision-log carry-over included.
- Expired sandboxes: existing workspace-recreate path invoked transparently
  on next message.
- Phase transitions idempotent, enforced by the transition matrix;
  plan approval idempotent and audited.
- Narration sidecar is best-effort: its failure never blocks or degrades the
  underlying run; the raw transcript is always available.

### Testing strategy

- Unit: thread transition matrix (mirroring ticket-transition tests);
  plan-gate semantics (approve, edit, skip).
- API: create/approve/implement flows; one-active-thread-per-subject;
  group thread closes members on merge.
- Contract: narration sidecar — fixed `events.jsonl` in, well-formed
  narration events with valid seq ranges out; template fallback path.
- Contract: decision-log distillation — transcript in, structured log out.
- E2E: thread happy path (refine → plan approve → implement → PR) with the
  `manual` executor so CI needs no LLM.
- MCP connect: auth-scoping tests (personal token cannot exceed role;
  tool allowlist enforced).

## Phasing

1. **Core thread:** entity + API + thread view; interactive refine session
   with question-asking prompt; plan soft gate; implement with decision-log
   carry-over; unified steering; "Test locally" button.
2. **Narration sidecar** + expandable feed.
3. **Review/fix polish:** verdict/finding cards, discuss-a-finding,
   fix-from-thread.
4. **Test recipes + ticket test artifacts** (doc conventions + DoD
   enforcement in playbooks) and **`opensweep connect`** user-scoped MCP.
5. **Group flows:** thread on parent → one branch/PR closing subtickets.
6. **Preview environments:** separate spec.

## Out of scope

- Platform preview environments (follow-up spec).
- Changes to review independence, convergence predicate, sandbox security
  model, or executor adapters.
- Cloud-overlay features; if metering threads is needed, add extension
  points here with allow-everything defaults per the open-core rules.
