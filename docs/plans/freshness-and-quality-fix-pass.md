# Fix Pass — Freshness Loop, Perf, Honesty, Bugs, Tests

One-pass remediation of the evaluation findings. **No backwards compatibility** — rename
fields, change tool signatures/DTOs, drop dead code, no migration shims. Dev data is
disposable (`infrastructure/dev_reset.py` exists); reseed rather than migrate.

Decisions locked with the user:
- **Freshness model:** unify to ONE derived staleness axis; stale clears only on human
  edit, accepted edit, or explicit agent confirmation. A code-quality audit does **not**
  clear docs-stale (auditing code ≠ verifying doc accuracy).
- **Tests:** stand up a Neo4j integration harness + write the P0/P1 tests.

Phases are ordered so each builds on the last. Land Phase 0–1 as the core; 2–6 are
independent and parallelizable after.

---

## Phase 0 — Shared freshness helper (unblocks Phase 1)

`doc_freshness.py` and `area_freshness.py` are near-verbatim duplicates.

- New `back_end/domains/repositories/services/path_matching.py` (or `infrastructure/paths.py`):
  move `_normalize`, `watches_path`, `_MAX_STALE_PATHS`, and a generic
  `mark_nodes_stale(nodes, changed_paths, watch_attr, now)` that stamps
  `code_changed_at` + accumulates `stale_paths`.
- `doc_freshness.mark_docs_stale` / `area_freshness.mark_areas_stale` become thin callers.
- Delete the duplicated `_normalize`/`_MAX_STALE_PATHS` from both freshness modules.
- Update `area_service.py`/`doc_service.py` imports of `watches_path` to the new module.

---

## Phase 1 — Close the freshness loop (headline fix)

**Goal:** one derived staleness signal, a symmetric confirm path for docs *and* areas, a
retirement path for docs, and no competing "freshness" definitions.

### 1a. Single staleness axis
- Keep `code_changed_at > last_reviewed_at` as the ONE derived "needs review" signal
  (`doc_is_stale` / `area_is_stale`). This is what the UI badge shows.
- **Demote `Checked` stamps to audit-coverage history only.** They stop being a second
  "freshness" surface:
  - `checked_service.freshness()` (`checked_service.py:159`) — delete or rename to
    `audit_coverage()` and stop exposing a "changed_since" flag that competes with the
    stale badge. The UI reads staleness from the Doc/Area DTO, coverage from stamps.
  - `audit_selection.rank_targets` (`audit_selection.py:40`) — keep "never audited" from
    Checked stamps, but rank "stale" pages by the **review axis** (`code_changed_at >
    last_reviewed_at`) instead of `code_changed_at > last_checked`. Now the auto-audit
    loop and the badge agree.
- Remove the now-dead `PageInfo.last_checked`-vs-`code_changed_at` staleness branch;
  `select_audit_targets` loads `last_reviewed_at` onto `PageInfo`.

### 1b. `confirm_area_current` (symmetry with docs)
- `area_freshness.confirm_area_current(repository_uid, key)` — mirror
  `doc_freshness.confirm_doc_current`: stamp `last_reviewed_at`, clear `stale_paths`.
- New platform tool `platform_tools/areas_tools.py::confirm_area_current` (mirror
  `docs_tools.py:95`).
- Register in `platform_tools/dispatcher.py` (add to imports + `_TOOLS` map, ~`:67`) and
  advertise in `executors/prompt_kit.py` `PLATFORM_WRITE_TOOLS` (`:45`, next to
  `confirm_doc_current`).
- Update the map/document run intents (`sweep.py` `_map_areas_intent`) to instruct the
  agent: after verifying an area is still correctly partitioned, call
  `confirm_area_current` instead of proposing a no-op edit.

### 1c. Doc retirement path (parity with Area `enabled=false`)
- Add `archived: BooleanProperty(default=False, index=True)` to `Doc` (models.py) — or a
  `DocEdit.proposed_archived` flag applied on accept, matching `AreaEdit.proposed_enabled`.
  Prefer the edit-flag route so retirement stays a reviewed proposal.
- `propose_doc_edit` accepts `archived: bool`; `accept_doc_edit` applies it.
- `list_docs`, `docs_watching_paths`, `repo_export.export_docs_to_repo`, briefing, and
  `select_audit_targets` exclude archived pages.
- Frontend: surface a "proposes retiring" badge on doc-edit review (mirror area card).

### 1d. Kill the divergence, document the model
- Update the module docstrings in `doc_freshness.py`/`area_freshness.py` and the KNOWLEDGE
  doc: "stale = needs review (code moved since last review). Cleared by edit / accepted
  edit / confirm_*_current. Checked stamps are audit coverage, not freshness."

---

## Phase 1B — Feature & sub-feature audits + specs *(new scope)*

**Grounding — what already exists (do not rebuild):** `full` campaigns already emit one
`feature` part per feature area with the `implementation-gaps` lens, and
`part_dispatch.py:142` inlines the feature's `Area.spec` as the contract to verify. Feature
areas already carry `spec`. Gaps: features are treated **flat** (no hierarchy/rollup),
specs are **never generated/maintained** (a no-spec feature is silently skipped at
`part_dispatch.py:143`), and features are **only audited in `full` scope** (rotation/focused
emit none). Decisions locked: **hierarchical sub-features with rollup** + **a
generate/refresh spec flow**.

Depends on Phase 1 (freshness) and the Area model.

### 1B-a. Feature hierarchy (sub-features with rollup)
- Extend leaf semantics to **feature** areas: reuse `is_leaf` / `child_key_prefix_of` but
  compute leaf-ness within the feature set (a feature is a leaf when no enabled feature key
  nests under it). Parent features = groupings (spec is an optional charter); sub-feature
  **leaves** are the audit targets.
- `campaign_service.py:134` — select feature **leaves** (not all features flat) for
  `feature_parts`; parent features aggregate.
- `finalize.build_summary` — parent-feature health = rollup of its sub-feature leaves'
  latest Checked stamps.
- `area_detail` / related-areas — render sub-feature children under a parent feature;
  parent shows aggregated coverage. Keep features exempt from partition-overlap warnings
  (they're overlays).

### 1B-b. Feature spec generation + maintenance (`run_generate_specs`)
- New `sweep.run_generate_specs` (analog to `run_generate_docs`): gated on a feature map
  existing; dispatches an agent that drafts specs for feature **leaves** lacking one and
  refreshes **stale** feature specs, landing as `propose_area_edit` proposals
  (`proposed_spec`) for human accept.
- New `_generate_specs_intent` + a spec-author contract; seed the agent in
  `agents/services/seed_defaults` (or reuse the doc-generation agent with a feature-spec
  contract).
- Feature specs join the freshness loop from Phase 1 — `confirm_area_current` clears feature
  staleness; spec-stale feature leaves become generate/refresh targets.
- `part_dispatch.py:143` — keep the "no spec → skip" guard, but emit a visible signal
  (finding/notification "feature `X` has no spec — run generate-specs") instead of a silent
  degrade; `run_generate_specs` targets exactly those.

### 1B-c. Features in every audit scope (not just `full`)
- `planner.build_plan` — include stale feature **leaves** as `feature` parts in `rotation`
  and `focused`, driven by the unified staleness axis (Phase 1a).
- `run_auto_audit` / `select_audit_targets` — extend target selection beyond Doc pages to
  stale feature leaves (→ implementation-gaps audit). Closes "features never auto-re-audited."

### 1B-d. Frontend
- Areas view: render the feature hierarchy (parent → sub-features) as a tree, like
  subsystems.
- Feature detail: show/edit the `spec`, its stale state, aggregated coverage for parents,
  and a "generate/refresh spec" action.
- Surface the "no spec → audit skipped" warning with a button to trigger generate-specs.

---

## Phase 2 — Performance: `.nodes.all()` → `.nodes.filter()` sweep

Correct today, but full-table scans across tenants. Fix the **real-problem** sites (skip
the classified-acceptable ones: global/system tables, seeders, background scanners that
must see all tenants).

**Priority 1 — hot path, biggest win:**
- `area_service.propose_area_edit` (`area_service.py:426`) — currently ~3–4 full scans per
  call (quadratic during a map-areas run). Fix:
  - `get_area_by_key` (`:137`) → `Area.nodes.filter(repository_uid=r, key=k)`.
  - `_repo_area_rows` (`:606`) → `Area.nodes.filter(repository_uid=r)`.
  - both `AreaEdit.nodes.all()` dedupe/partition loops (`:459`, `:491`) →
    `AreaEdit.nodes.filter(repository_uid=r, status="pending")`.
- Same treatment for `doc_service` (`list_docs`, `get_doc_by_slug`, `count_pending_new_pages`,
  `list_doc_edits`, `propose_doc_edit`, `reset_docs`, `delete_doc` non-Memory scan).

**Priority 2 — per-run agent tools & list endpoints:**
- `platform_tools/docs_tools.py:24`, `read_findings.py:54,85`, `prior_findings.py:23`,
  `findings/queries.py:13` (`find_similar`), `finding_service.list:114`.
- `api/v1/runs.py:302` (`list_runs`), `api/v1/sweep.py:267`, `analysis_service.list:153`.
- `analysis_service._attach_finding_rollup:134` → `Finding.nodes.filter(source_run_uid=...)`
  (also a discrete bug — see Phase 4).

**Priority 3 — freshness webhooks:**
- `doc_freshness.docs_watching_paths:60` / `mark_docs_stale:85`, `area_freshness:53` →
  filter by `repository_uid` (folds into the Phase 0 shared helper).

Leave acceptable sites untouched; add a one-line comment where an `.all()` is intentional
(global table / all-tenant scanner) so it doesn't get "fixed" later.

---

## Phase 3 — Stop presenting degraded results as success

- **Killed partial deep-scan:** `analysis_service.finalize_analysis_for_run` (`:63`) must
  distinguish a self-finalized scan (agent called `upsert_analysis` with a verdict) from a
  forced finalize. On forced finalize, set `status="incomplete"` (new status) — do **not**
  assign/keep a `health_grade`, and stamp `limitations="scan did not complete"`. Health
  UI (`latest_for_repo`, `HealthView`) treats `incomplete` as "no current grade."
- **Degraded planning:** `campaigns/.../planner.normalize_areas` — when the file tree is
  unavailable, set a `degraded: true` flag on the plan/campaign and refuse to auto-dispatch
  a full audit against a guessed partition (or dispatch but mark the run `degraded`). Don't
  silently mis-partition and report success.
- **Degraded composition:** `executors/.../composition.py` resolvers currently swallow all
  exceptions → fallback prompt. Add a `composed_degraded` marker on the Run when any layer
  fell back, surface it on the run detail, and log at `error` not `warning`.
- **Auto-audit retry thrash:** `agents/.../schedule_scanner.py:92` — stamp
  `sa.last_scheduled_at = moment` in the `audit-stale` failure branch, matching every
  sibling branch. One-line fix; prevents every-beat retries.

---

## Phase 4 — Discrete bugs

**Frontend:**
- `components/areas/AreaEditReviewCard.vue:35` — change `v-else` → `v-else-if="edit.area_uid"`
  so new-area proposals don't render both "new area" and "updates existing". (Verified bug.)
- `stores/docStore.ts:216-228` — `bulkAccept`/`bulkReject` must honor the server's
  `result.accepted`/`errors` (mirror `areaStore.ts:88-94`), not blindly drop every requested
  uid.
- Area-edit review UX: render a **spec diff** (reuse `lib/lineDiff.ts`, the DTO already
  carries `current_spec`) and a scope-path added/removed diff; show partition `warnings`
  **before** accept (the propose result already returns them — thread them into the edit DTO
  or refetch on open). Extract a `DocEditReviewCard.vue` to kill the duplicated diff block in
  `DocumentationView.vue` (~120 lines).
- `analysisStore.ts:112` — add the missing generic to `apiPost` in `refineWithAnswers`;
  move the hand-mirrored Analysis DTOs into `types/api.ts`; dedupe `daysAgo` into
  `lib/utils.ts`.

**Backend:**
- `analysis_service._attach_finding_rollup:134` — filter by `source_run_uid` (Phase 2).
- `platform_tools/areas_tools.propose_area_edit:26` — drop the unused `executor` param.
- `complete_run.py` / `submit_thread_plan.py:40` — stop overloading the `executor` kwarg as
  a run/thread id; pass an explicit `run_uid`. (No-back-compat: change the signature.)

---

## Phase 5 — Neo4j test harness + P0/P1 tests

- **Harness:** extend `tests/conftest.py` — a session-scoped fixture that connects to the
  dev Neo4j (or a throwaway test DB), gated on the existing `neo4j_available` probe
  (skip when absent), with per-test cleanup of created nodes. Wire `config_for_test` so
  neomodel points at the test DB.
- **P0 — freshness core:**
  - `mark_docs_stale`: matching docs stamped + `stale_paths` accumulated (deduped, capped at
    `_MAX_STALE_PATHS`), non-matching untouched, per-doc error isolation.
  - `confirm_doc_current` / `confirm_area_current`: clears `stale_paths`, advances
    `last_reviewed_at`, unknown slug/key → None.
  - End-to-end: push webhook → stale badge true → confirm → stale badge false.
- **P1 — analysis/health integrity:**
  - `_attach_finding_rollup` + `latest_for_repo`: by-severity rollup, repo isolation,
    superseded exclusion + newest-first, `incomplete` excluded from grade.
  - `finalize_analysis_for_run` idempotency + the new incomplete path;
    `get_or_create_analysis` uniqueness race.
- **P1 — docs export:** `export_docs_to_repo` path allowlist, orphan managed-file deletion
  vs preserving hand-written files (can test the pure render/merge + a mocked sandbox).
- **Regression:** unified audit-target ranking (Phase 1a) agrees with the stale badge.
- **P1 — features (Phase 1B):** feature-leaf selection + parent-grouping exclusion;
  parent-feature coverage rollup; `run_generate_specs` targets exactly no-spec/stale feature
  leaves; feature parts appear in rotation/focused when stale; `part_dispatch` no-spec skip
  emits the visible signal instead of a silent degrade.

---

## Phase 6 — Cleanup

- Remove `composition.py` duplicate `_render_repo_guidance` import/call (`:124`).
- Remove misattributed comment blocks in `areaStore.ts:104` / `docStore.ts:114`.
- Confirm `sweep.py:849 estimate_sweep_cost` is still referenced; delete if orphaned.
- Grep for now-dead references to the removed `checked_service.freshness` / `last_checked`
  staleness branch and delete.

---

## Sequencing & verification

1. Phase 0 → 1 (core; land together, they're one conceptual change).
2. Phase 1B (features/sub-features/specs) — builds on Phase 1; land as its own reviewable
   unit (touches areas + campaigns + a new run flow + frontend tree).
3. Phase 2, 3, 4-backend in parallel (independent).
4. Phase 4-frontend.
5. Phase 5 last (tests the above); run `pytest` from `back_end/` and `pnpm build` +
   `vue-tsc` for the frontend.

**Definition of done:** freshness is a closed loop (push → stale → audit/confirm → fresh)
with one definition; features and sub-features are first-class (hierarchical, spec'd,
audited in every scope, specs generated + kept current, no silent no-spec skips); no
hot-path full-table scans in the map/docs/findings paths; degraded runs are visibly
degraded, never "success"; the verified bugs are fixed; the P0/P1 integration tests pass
against a real Neo4j.
