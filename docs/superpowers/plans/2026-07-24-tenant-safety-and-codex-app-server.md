# Tenant-Safety Hardening + Codex App-Server Enablement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the org-tenancy boundary (query-level provider scoping + cross-org read-path regression tests) and lay the verified foundation for running codex concurrently on one subscription via its `app-server`, behind the existing `codex_cli` seam.

**Architecture:** Three shippable phases (1–3) plus a gated design phase (4). Phase 1 converts provider reads from fetch-all-then-Python-filter to indexed `.nodes.filter(org_uid=…)`. Phase 2 locks the cross-org read boundary with regression tests + a gap audit. Phase 3 is an executable spike that verifies the two unknowns blocking the app-server. Phase 4 (the app-server build) is authored **from the spike's recorded protocol handshake** — its per-step detail is intentionally deferred because writing JSON-RPC steps against an unverified experimental protocol would be inventing them.

**Tech Stack:** Python 3.13, FastAPI, neomodel (async) over Neo4j, pytest (`asyncio_mode=auto`), codex-cli 0.145.0.

## Global Constraints

- **Two-repo rule:** All shared product code lands in `opensweep/` (public); the cloud overlay merges via `git fetch upstream && git merge upstream/main`. No `if cloud:` branches in shared files — add an extension point with a safe default here, implement cloud specifics in the overlay. (`opensweep/CLAUDE.md`)
- **Tenancy invariant:** Repository is the tenancy boundary; every scoped read reduces to `require_repo_in_org(entity.repository_uid, user.org_uid)` (404, never 403, so existence never leaks). (`domains/tenancy.py`)
- **Providers are strictly org-owned:** `org_uid == ""` rows are legacy-unowned and invisible/unusable to everyone. (`domains/llm_providers/services/llm_provider_service.py:3-7`)
- **Codex isolation:** OpenSweep is the sandbox; codex runs `--dangerously-bypass-approvals-and-sandbox` (`sandbox: danger-full-access` in app-server terms). Credentials never reach repo-tool code's env (allowlist model, `domains/executors/agent_env.py`).
- **Behavior-preserving refactors keep existing tests green:** `test_llm_provider_tenancy.py`, `test_tenancy.py`, `test_codex_cli.py`, full suite (1679 passing baseline).
- **Test venv:** `/Users/jeroenbrouns/Desktop/opensweep-both/opensweep/back_end/.venv/bin/python -m pytest` (run from `back_end/`).

---

## File Structure

- `domains/llm_providers/services/llm_provider_service.py` — provider tenancy reads (Phase 1). One responsibility: org-scoped provider selection.
- `domains/runs/services/lifecycle.py` — resume fallback exclusion set (Phase 1, minor tidy).
- `tests/test_llm_provider_tenancy.py` — provider scoping tests (Phase 1 additions).
- `tests/test_read_path_tenancy.py` — NEW: cross-org 404 regression tests for the run/artifact read surface (Phase 2).
- `docs/superpowers/spikes/2026-07-24-codex-app-server.md` — NEW: spike protocol + findings (Phase 3).
- `domains/llm_providers/services/codex_cli.py` — the seam the app-server plugs into (Phase 4; interface extension only in the public repo).

---

## Phase 1 — Provider reads use query-level org scoping

**Why:** `repository_service` scopes in the DB query (`Repository.nodes.get_or_none(uid, org_uid)`), but provider reads do `[n for n in await LLMProvider.nodes.all() if _scope(n) == org_uid]` — loading *every org's* rows then filtering in Python. `LLMProvider.org_uid` is already `index=True` (`models.py:23`), so `.nodes.filter(org_uid=…)` is a drop-in that makes isolation structural (a forgotten filter can't leak) and avoids loading foreign rows into memory. Behavior is identical; existing tenancy tests are the guard.

**Do NOT convert** `credentials.py:encrypt_plaintext_provider_secrets` (line 36) — its `LLMProvider.nodes.all()` is an *intentional* all-orgs maintenance pass (idempotent re-seal on key rotation). Leave it, and add a comment marking it deliberate.

### Task 1.1: Convert `visible_providers` and `_scope_active` to indexed filter

**Files:**
- Modify: `domains/llm_providers/services/llm_provider_service.py:49-54` (`visible_providers`), `:270-273` (`_scope_active`)
- Test: `tests/test_llm_provider_tenancy.py`

**Interfaces:**
- Consumes: `LLMProvider.nodes.filter(org_uid=…)` (async neomodel, returns an awaitable resolving to an iterable — same call `repository_service.py:27` uses).
- Produces: unchanged signatures — `visible_providers(org_uid: str) -> list[LLMProvider]`, `_scope_active(scope: str) -> LLMProvider | None`.

- [ ] **Step 1: Write the failing test** (asserts scoping no longer loads foreign rows — spy on `nodes.all` vs `nodes.filter`)

```python
# tests/test_llm_provider_tenancy.py
async def test_visible_providers_queries_by_org_not_fetch_all(monkeypatch):
    import domains.llm_providers.services.llm_provider_service as svc

    called = {"all": 0, "filter_org": None}

    class _FakeNodes:
        async def all(self):
            called["all"] += 1
            return []

        async def filter(self, **kw):
            called["filter_org"] = kw.get("org_uid")
            return []

    monkeypatch.setattr(svc.LLMProvider, "nodes", _FakeNodes())
    await svc.visible_providers("org-a")
    assert called["all"] == 0, "must not fetch all orgs' providers"
    assert called["filter_org"] == "org-a"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_llm_provider_tenancy.py::test_visible_providers_queries_by_org_not_fetch_all -v`
Expected: FAIL — `called["all"] == 1` (current code calls `.all()`).

- [ ] **Step 3: Convert both reads to `.filter(org_uid=…)`**

```python
# visible_providers (was: return [n for n in await LLMProvider.nodes.all() if _scope(n) == org_uid])
async def visible_providers(org_uid: str) -> list[LLMProvider]:
    """The org's own providers, nothing else. A caller without an org sees
    none — legacy-unowned rows (org_uid == "") are invisible to everyone."""
    if not org_uid:
        return []
    return list(await LLMProvider.nodes.filter(org_uid=org_uid))
```

```python
# _scope_active (was: nodes = [n for n in await LLMProvider.nodes.all() if _scope(n) == scope])
async def _scope_active(scope: str) -> LLMProvider | None:
    """The usable active provider WITHIN one org scope, healing old data
    with multiple actives in that scope."""
    if not scope:
        return None
    nodes = list(await LLMProvider.nodes.filter(org_uid=scope))
    enabled = [p for p in nodes if bool(getattr(p, "enabled", True))]
    active = [p for p in enabled if bool(getattr(p, "active", False))]
    if not active:
        return None
    winner = active[0]
    for p in active[1:]:
        p.active = False
        await p.save()
    if (winner.last_health_status or "unknown") == LLMProviderHealth.UNREACHABLE.value:
        return None
    return winner
```

- [ ] **Step 4: Run the new test + the full provider tenancy suite**

Run: `.venv/bin/python -m pytest tests/test_llm_provider_tenancy.py -v`
Expected: PASS (new test + all existing `test_list_shows_own_org_only`, `test_selection_never_uses_other_orgs_provider`, etc.).

- [ ] **Step 5: Commit**

```bash
git add domains/llm_providers/services/llm_provider_service.py tests/test_llm_provider_tenancy.py
git commit -m "Scope provider reads by org at the query, not in Python"
```

### Task 1.2: Convert `_deactivate_others` and `_ensure_one_active`; mark the intentional all-orgs pass

**Files:**
- Modify: `domains/llm_providers/services/llm_provider_service.py:345-347` (`_deactivate_others`), `:352-356` (`_ensure_one_active`)
- Modify: `domains/llm_providers/services/credentials.py:36` (comment only)

**Interfaces:**
- Consumes: `LLMProvider.nodes.filter(org_uid=scope)`.
- Produces: unchanged signatures.

- [ ] **Step 1: Convert both scoped writes to filter**

```python
# _deactivate_others (was: for p in await LLMProvider.nodes.all(): ... if _scope(p) == scope ...)
async def _deactivate_others(active_uid: str, scope: str) -> None:
    for p in await LLMProvider.nodes.filter(org_uid=scope):
        if p.uid != active_uid and bool(getattr(p, "active", False)):
            p.active = False
            await p.save()
```

```python
# _ensure_one_active (was: nodes = [p for p in await LLMProvider.nodes.all() if _scope(p) == scope])
    nodes = list(await LLMProvider.nodes.filter(org_uid=scope))
    candidate = choose_provider(nodes)
```

- [ ] **Step 2: Mark the deliberate all-orgs maintenance loop**

```python
# credentials.py:encrypt_plaintext_provider_secrets — add above the loop:
    # Deliberate all-orgs pass: key rotation re-seals EVERY provider's secret,
    # so this is not org-scoped (unlike llm_provider_service reads). Do not
    # convert to a per-org filter.
    for provider in await LLMProvider.nodes.all():
```

- [ ] **Step 3: Run the provider suites**

Run: `.venv/bin/python -m pytest tests/test_llm_provider_tenancy.py tests/test_provider_fallback.py tests/test_provider_credential_seal.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add domains/llm_providers/services/llm_provider_service.py domains/llm_providers/services/credentials.py
git commit -m "Query-scope active-provider heal writes; document the intentional all-orgs re-seal"
```

### Task 1.3: Tidy the resume fallback exclusion set to the run's org

**Files:**
- Modify: `domains/runs/services/lifecycle.py:946-952`

**Interfaces:**
- Consumes: `repository_org_uid(run.repository_uid)` (already imported in this function), `LLMProvider.nodes.filter(org_uid=…)`.
- Produces: unchanged behavior (the exclude set is only ever applied by `select_provider(org_uid=…)`, so scoping it is a tidy, not a fix).

- [ ] **Step 1: Scope the write-support exclusion scan to the run's org**

```python
        run_org = await repository_org_uid(run.repository_uid)
        # Only the run's org's providers can ever be selected below, so build the
        # write-support exclusion from that org (not every org's rows).
        exclude |= {
            (p.uid or "").strip()
            for p in await LLMProvider.nodes.filter(org_uid=run_org)
            if not _provider_supports_write(p)
        }
    provider = await select_provider(org_uid=run_org, exclude_uids=exclude)
```

- [ ] **Step 2: Run resume/lifecycle tests**

Run: `.venv/bin/python -m pytest tests/ -q -k "lifecycle or resume or provider_fallback or run_create_tenancy"`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add domains/runs/services/lifecycle.py
git commit -m "Scope resume write-support exclusion scan to the run's org"
```

### Task 1.4: Guard against regressions — no `.nodes.all()` in provider scoping

**Files:**
- Test: `tests/test_llm_provider_tenancy.py`

- [ ] **Step 1: Write a source-level guard test**

```python
def test_provider_scoping_never_fetches_all_orgs():
    """Scoped reads must query by org_uid, not load every org's providers.
    The ONE deliberate all-orgs pass is the credential re-seal (guarded by name)."""
    from pathlib import Path
    src = Path("domains/llm_providers/services/llm_provider_service.py").read_text()
    assert "LLMProvider.nodes.all()" not in src, (
        "provider scoping must use .nodes.filter(org_uid=...); the only allowed "
        ".nodes.all() is credentials.encrypt_plaintext_provider_secrets"
    )
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/test_llm_provider_tenancy.py::test_provider_scoping_never_fetches_all_orgs -v`
Expected: PASS (Tasks 1.1–1.2 removed all `.nodes.all()` from this file).

- [ ] **Step 3: Commit**

```bash
git add tests/test_llm_provider_tenancy.py
git commit -m "Guard: provider scoping never fetches all orgs"
```

---

## Phase 2 — Cross-org read-path regression tests + gap audit

**Why:** The read boundary is already enforced — `runs.py` calls `require_repo_in_org` on `get_run`, `get_transcript`, `get_run_changes`, `run_ws`, and `artifacts.py` org-checks the embedded repo uid before serving a blob. But there is **no regression test** proving a foreign org gets 404, and no systematic check that a *future* endpoint can't skip it. This phase locks the boundary and audits for gaps.

### Task 2.1: Audit every api/v1 read handler for org enforcement

**Files:**
- Create: `docs/superpowers/spikes/2026-07-24-readpath-authz-audit.md` (the audit record)

- [ ] **Step 1: Enumerate every GET/WS handler and its authz call**

Run:
```bash
cd back_end && for f in api/v1/*.py; do
  echo "== $f =="
  grep -nE "@router\.(get|websocket)|require_repo_in_org|org_repo_uids|require_role|get_current_user" "$f"
done | tee /tmp/authz_audit.txt
```
Expected: a per-file list pairing each GET/WS route with its authz calls.

- [ ] **Step 2: Record findings**

Write `docs/superpowers/spikes/2026-07-24-readpath-authz-audit.md` listing, for each GET/WS route: `path` · `authz = require_repo_in_org | org_repo_uids-filter | none`. Flag any route returning run/repo/artifact/finding/analysis/thread data with `authz = none`. (Expectation from inspection: runs + artifacts are covered; verify findings/analysis/areas/threads/sandboxes/tickets.)

- [ ] **Step 3: Commit the audit**

```bash
git add docs/superpowers/spikes/2026-07-24-readpath-authz-audit.md
git commit -m "Audit: api/v1 read-path org enforcement coverage"
```

### Task 2.2: Cross-org 404 regression tests for the run/artifact read surface

**Files:**
- Create: `tests/test_read_path_tenancy.py`
- (If Task 2.1 found a gap) Modify the offending `api/v1/*.py` handler to add `await require_repo_in_org(node.repository_uid, user.org_uid)`.

**Interfaces:**
- Consumes: the FastAPI app + test client fixture used by existing route tests (mirror `tests/test_llm_provider_routes.py` / `test_run_create_tenancy.py` setup — two orgs, a repo in org-a, a user in org-b).

- [ ] **Step 1: Write cross-org 404 tests for run detail, transcript, changes, and artifact**

```python
# tests/test_read_path_tenancy.py
"""A user in org-b must get 404 (never data, never 403) for org-a resources."""
import pytest

from tests.helpers.routes import make_client, seed_repo, seed_run, user_in_org  # mirror existing route tests


@pytest.mark.parametrize("path_tmpl", [
    "/api/v1/runs/{run_uid}",
    "/api/v1/runs/{run_uid}/transcript",
    "/api/v1/runs/{run_uid}/changes",
])
async def test_foreign_org_gets_404_on_run_reads(path_tmpl):
    repo = await seed_repo(org_uid="org-a")
    run = await seed_run(repository_uid=repo.uid)
    client = make_client(user=user_in_org("org-b"))
    resp = await client.get(path_tmpl.format(run_uid=run.uid))
    assert resp.status_code == 404


async def test_foreign_org_gets_404_on_artifact():
    repo = await seed_repo(org_uid="org-a")
    run = await seed_run(repository_uid=repo.uid)
    uri = f"opensweep-artifact://{repo.uid}/{run.uid}/raw_transcript.txt"
    client = make_client(user=user_in_org("org-b"))
    resp = await client.get(f"/api/v1/artifacts?uri={uri}")
    assert resp.status_code == 404
```

> **Note for the implementer:** OpenSweep's route tests do not use a shared `tests/helpers/routes` module yet — before writing Step 1, open `tests/test_run_create_tenancy.py` and `tests/test_llm_provider_routes.py`, copy their actual client + seeding fixtures inline, and replace the `from tests.helpers.routes import …` line with those. Keep the assertions above verbatim.

- [ ] **Step 2: Run — expect PASS if the boundary holds, FAIL if a gap exists**

Run: `.venv/bin/python -m pytest tests/test_read_path_tenancy.py -v`
Expected: PASS for runs/artifacts (already enforced). Any FAIL = a real gap → fix the handler (add `require_repo_in_org`) and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/test_read_path_tenancy.py api/v1/
git commit -m "Regression tests: cross-org run/artifact reads 404"
```

### Task 2.3: Cross-org rejection test for the run WebSocket

**Files:**
- Modify: `tests/test_read_path_tenancy.py`

- [ ] **Step 1: Assert the WS closes for a foreign org**

```python
async def test_foreign_org_ws_is_rejected():
    repo = await seed_repo(org_uid="org-a")
    run = await seed_run(repository_uid=repo.uid)
    client = make_client(user=user_in_org("org-b"))
    with pytest.raises(Exception):  # require_repo_in_org raises 404 → WS handshake fails
        async with client.websocket_connect(f"/api/v1/runs/{run.uid}/ws"):
            pass
```

- [ ] **Step 2: Run**

Run: `.venv/bin/python -m pytest tests/test_read_path_tenancy.py::test_foreign_org_ws_is_rejected -v`
Expected: PASS (`run_ws` calls `require_repo_in_org` at `runs.py:757`).

- [ ] **Step 3: Commit**

```bash
git add tests/test_read_path_tenancy.py
git commit -m "Regression test: cross-org run websocket rejected"
```

### Task 2.4: Land Phases 1–2 to both repos

- [ ] **Step 1: Full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass (≥ 1679 + new).

- [ ] **Step 2: Push public, merge cloud**

```bash
git push origin main
cd ../../opensweep-cloud && git fetch upstream && git merge upstream/main && \
  /Users/jeroenbrouns/Desktop/opensweep-both/opensweep/back_end/.venv/bin/python -m pytest back_end/tests/test_llm_provider_tenancy.py back_end/tests/test_read_path_tenancy.py -q && \
  git push origin main
```
Expected: cloud merge clean (shared code, no overlay divergence), tests pass, pushed.

---

## Phase 3 — Codex app-server spike (GATE for Phase 4)

**Why:** The app-server dissolves the auth-serialization problem (one process owns the credential and refreshes centrally) but rides an **experimental** protocol with two unverified assumptions. This spike records the real handshake and answers both, producing the facts Phase 4's steps are written from. **Do not start Phase 4 until this phase's decision is recorded.**

The verified facts so far (from `codex app-server generate-json-schema`, codex-cli 0.145.0): `ThreadStart` takes per-thread `cwd`, `sandbox` (`read-only|workspace-write|danger-full-access`), `approvalPolicy`, `model`, `config`; `TurnStart` + `TurnEnvironmentParams { cwd, environmentId }`; streaming via `AgentMessageDeltaNotification` / `TurnCompletedNotification`; `ChatgptAuthTokensRefresh` is a first-class method; transports `stdio://ptr`, `unix://`, `ws://`.

### Task 3.1: Stand up the daemon and drive two concurrent threads on two worktrees

**Files:**
- Create: `docs/superpowers/spikes/2026-07-24-codex-app-server.md` (protocol log + findings)

- [ ] **Step 1: Seed a throwaway CODEX_HOME and start the app-server on a unix socket**

```bash
export SPIKE_HOME=$(mktemp -d)/codex && mkdir -p "$SPIKE_HOME"
cp ~/.codex/auth.json "$SPIKE_HOME/auth.json"   # throwaway copy — spike only
CODEX_HOME="$SPIKE_HOME" codex app-server --listen unix:///tmp/codex-spike.sock &
```
Expected: server starts, socket appears. Record startup lines in the spike doc.

- [ ] **Step 2: Create two git worktrees and open a thread per worktree, concurrently**

Drive the JSON-RPC protocol (via a small throwaway client — `websocat`/`socat` or a 30-line Python asyncio socket client): `ThreadStart{ cwd: <worktreeA>, sandbox: "danger-full-access" }` and `ThreadStart{ cwd: <worktreeB>, … }`, then `TurnStart` in each with a prompt like "list the files here and stop". Record: both `threadId`s, both `AgentMessageDelta` streams, both `TurnCompleted`. **Record the exact request/response JSON in the spike doc** (this is what Phase 4's client is coded against).

- [ ] **Step 3: Verify central refresh — no cross-thread rotation error**

Confirm both threads complete with **no** "access token could not be refreshed". Capture whether the server emitted `ChatgptAuthTokensRefresh` activity and whether `auth.json` `tokens.access_token` changed once (central) vs. raced. Record.

- [ ] **Step 4: Commit the protocol log**

```bash
git add docs/superpowers/spikes/2026-07-24-codex-app-server.md
git commit -m "Spike: codex app-server drives two concurrent worktree threads"
```

### Task 3.2: Verify access-token-only viability and measure token lifetime

**Files:**
- Modify: `docs/superpowers/spikes/2026-07-24-codex-app-server.md`

- [ ] **Step 1: Measure the access-token lifetime**

Decode the `exp` claim of `tokens.access_token` (JWT) from a throwaway `auth.json` and subtract `iat`/now. Record the lifetime in the doc. **Decision input:** is it comfortably greater than `TURN_TIMEOUT_SECONDS = 3600`?

- [ ] **Step 2: Test an access-token-only auth.json under `codex exec`**

Write a throwaway `auth.json` with `tokens.access_token` only (no `refresh_token`), point `CODEX_HOME` at it, run `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "print hello and stop"`. Record: does it run to completion on the bearer token, and at forced expiry does it fail **gracefully** (clean error) rather than crash/hang?

- [ ] **Step 3: Record the go/no-go decision**

In the doc, write the decision:
- **Model A (app-server-per-subscription):** if Task 3.1 showed clean concurrent threads + central refresh.
- **Model B (decoupled authority + per-run isolated exec, access-token-only):** requires Step 2 to pass AND (Step 1 lifetime > max run wall-time, OR a mid-run reseed path). Preferred for multi-tenant (preserves per-run isolation).
- Note the codex-cli version and protocol version for pinning.

- [ ] **Step 4: Commit the decision**

```bash
git add docs/superpowers/spikes/2026-07-24-codex-app-server.md
git commit -m "Spike: token lifetime + access-token-only viability; app-server model decision"
```

- [ ] **Step 5: Tear down**

```bash
kill %1 2>/dev/null; rm -rf "$SPIKE_HOME" /tmp/codex-spike.sock
```

---

## Phase 4 — App-server integration behind `codex_cli` (authored from Phase 3)

> **GATE:** Do not begin until `docs/superpowers/spikes/2026-07-24-codex-app-server.md` records a go decision and the exact `ThreadStart`/`TurnStart`/notification JSON. The per-step TDD detail below is deliberately **not** pre-written: coding JSON-RPC steps against an unverified experimental protocol would be inventing them (a plan failure). The moment the spike lands, extend this phase with the recorded shapes and re-run the writing-plans self-review.

**Locked design (independent of spike outcome):**

- **Isolation stays structural.** One credential authority = one subscription = one org. Execution stays per-run isolated (existing sandbox clone model). The app-server changes only *where the LLM token refreshes*, never the org boundary. (Prefer **Model B** from the spike for the multi-tenant cloud; **Model A** is acceptable for single-org/self-hosted.)
- **The seam is `codex_cli`.** Phase 4 adds one public extension point with a local default; the cloud overlay implements the fleet:

```python
# domains/llm_providers/services/codex_cli.py — NEW extension point (public repo, safe default)
async def acquire_run_credential(provider, *, run_uid: str) -> "CodexRunCredential":
    """Return the credential a single run should seed into its CODEX_HOME.

    Default (public / single subscription): today's behavior — the sealed
    auth.json under the per-subscription lease (codex_credential_txn).
    Overlay (cloud): a short-lived, access-token-only credential minted by the
    per-subscription authority, so runs never rotate and need no lease.
    """
```

**Task outline (granularity finalized post-spike):**

1. **`codex_cli.acquire_run_credential` extension point + local default.** Wrap today's `codex_credential_txn` seeding behind it; `_build_cli_env`/`codex_turn_env` call it instead of reading the sealed secret directly. TDD: default path reproduces current `test_cli_env_allowlist` + `test_codex_run_lease` behavior byte-for-byte.
2. **App-server client** (`codex_app_server_client.py`): a typed JSON-RPC client over the transport the spike validated, with exactly the `ThreadStart`/`TurnStart`/`AgentMessageDelta`/`TurnCompleted`/`ChatgptAuthTokensRefresh` shapes recorded in Phase 3. TDD against a recorded-fixture server.
3. **Per-subscription authority (cloud overlay)**: owns one `auth.json`, performs `ChatgptAuthTokensRefresh`, CAS-persists rotation (reuse `codex_credential`/`codex_auth` write-back), issues access-token-only creds over a per-subscription channel. Keyed by `provider_uid` the run already resolved org-scoped — never re-derives org. Egress-restricted; holds no GitHub tokens.
4. **Fleet/admission (cloud overlay)**: `provider_uid → authority` placement, warm pool, idle shutdown, health/restart with thread re-attach; per-subscription concurrency + turn-rate limiter mapping saturation to `PAUSED_QUOTA` (reuse the mechanism from the lease work).
5. **Retire per-run lease + `exec --json` parsing + continuation hack** where Model A/B makes them redundant (native resume replaces `codex_continuation_prompt`; `AgentMessageDelta` replaces `_codex_delta_feeder`) — behind the same seam, so the two orchestrators are untouched.
6. **Tenancy regression tests** extended to the new path: a run for org-a can only reach org-a's authority; access-token-only cred carries no refresh token; foreign-org routing is impossible by construction (per-subscription channel).

---

## Self-Review

**Spec coverage:**
- "Tighten provider reads to query-level scoping" → Phase 1 (Tasks 1.1–1.4). ✓
- "Audit the artifact/transcript read paths for org-scoping" → Phase 2 (Task 2.1 audit + 2.2–2.3 regression tests). ✓ (Finding: already enforced; phase locks it + closes any gap.)
- "Make the app-server work" → Phase 3 (spike, executable) + Phase 4 (gated build, design locked, steps authored post-spike). Honestly gated rather than fabricated. ✓
- "Don't leak files/repos/subscriptions between orgs" → Phase 1 (subscriptions structural), Phase 2 (files/repos read-path tests), Phase 4 design (authority per subscription, GitHub tokens stay per-run, per-run worktrees). ✓

**Placeholder scan:** Phases 1–3 contain complete code/commands with expected output. Phase 4's deferral is explicit and justified (unverified experimental protocol) — the one place without per-step code, by design and flagged as a gate, not a silent TODO.

**Type consistency:** `visible_providers(org_uid)->list`, `_scope_active(scope)->LLMProvider|None`, `require_repo_in_org(repository_uid, org_uid)`, `acquire_run_credential(provider, *, run_uid)` are used consistently across tasks. The Phase 2 tests depend on a client/seeding fixture the implementer copies from `test_run_create_tenancy.py` (flagged inline, not assumed to exist).

**Open dependency:** Phase 2 tests reuse existing route-test fixtures; if none are reusable, Task 2.2 Step 1's note directs copying them inline from the named files.
