## Task 9 Report — Frontend four-tier effort picker + policy surfaces

### Step 1 Discovery Findings

**Where effort values flow in the frontend:**

1. **AskView.vue** posts via `docs.audit(repoUid, [], { effort: effort.value })` → `POST /repositories/{uid}/sweep/audit` — this is the key path. The old UI sent `'small' | 'normal' | 'large'` as the `effort` field.

2. **Backend sweep/audit endpoint** (`back_end/api/v1/sweep.py`) receives `effort: InvestigationEffort = InvestigationEffort.NORMAL`. The `normalize_effort()` function maps `"quick"` → `SHORT` but does NOT map `"small"` or `"large"` — those would have fallen through to `NORMAL` as the default. So the old UI's `"large"` value was silently normalized to `"normal"` by the backend.

3. **Backend InvestigationEffort enum** (`back_end/domains/investigations/schemas.py`) now has four values: `SHORT="short"`, `NORMAL="normal"`, `DEEP="deep"`, `UNLIMITED="unlimited"`. Aliases: `{"quick": SHORT}`.

4. **AskView also sends `default_effort` to `/agent-prompts`** (line 123): `default_effort: effort.value` when saving a prompt. AgentPromptsView.vue and agentPromptStore.ts also handle `default_effort`.

5. **"small"/"large" never reached the backend as InvestigationEffort** — they went to the sweep endpoint which uses `InvestigationEffort` pydantic model. `"small"` and `"large"` would fail pydantic validation (not in the enum) or fall to the default. In practice, `normalize_effort` is also called with a validator — unrecognized values return `NORMAL`.

6. **seed_variants `default_effort` values**: `"light"` and `"deep"` appear in AgentPromptStore legacy code. Added `light: 'short'` mapping in the legacy dict.

7. **Other files with effort display**: `InvestigationDetailView.vue` shows `inv.effort` as raw string (no mapping needed — the backend stores the canonical enum value). `FindingDetailView.vue` uses `Effort` (the finding effort type `trivial|small|medium|large`) — unchanged since that's a different type. `WorkflowCard.vue` has `'quick'` in its ReviewDepth options (that's `ReviewDepth`, not `InvestigationEffort`) — untouched.

**No "small"/"large" values reach the backend InvestigationEffort fields currently** — the AskView sends them to sweep/audit which parses `InvestigationEffort`, causing silent fallback to `normal`. The new UI fixes this correctly.

### Files Modified

- `front_end/src/views/AskView.vue` — effort ref type changed to `'short' | 'normal' | 'deep' | 'unlimited'`; `pickPrompt()` now maps legacy values (`quick→short`, `small→short`, `light→short`, `large→deep`); SelectContent updated to four tiers.
- `front_end/src/types/api.ts` — `InvestigationEffort` updated to `'short' | 'normal' | 'deep' | 'unlimited' | 'quick'` (keeping `'quick'` for legacy response DTOs).
- `front_end/src/views/RunPoliciesView.vue` — added `formatCeiling(v, unit, isWall)` helper; ceiling display uses it: `max_wall_seconds === 0` → "Unlimited", `null` wall → "default (60m)", other null ceilings → "Unlimited".
- `front_end/src/stores/docStore.ts` — `audit()` option type updated from `'small' | 'normal' | 'large'` to `'short' | 'normal' | 'deep' | 'unlimited'`.
- `front_end/src/stores/agentPromptStore.ts` — `AgentPromptDTO.default_effort` type widened to include `'short' | 'unlimited'` alongside legacy values (kept for backward compat with existing rows).
- `front_end/src/views/admin/AgentPromptsView.vue` — Default effort select options updated to `short/normal/deep/unlimited`.
- `front_end/pnpm-lock.yaml` — updated by `pnpm install` to resolve lockfile/package.json specifier mismatch on this branch.

### Step 6 (Manual Smoke)

Deferred to Task 10 final verification as instructed.

### Build/Type-check

`cd front_end && npx vue-tsc --noEmit` — passes with zero errors or warnings.
