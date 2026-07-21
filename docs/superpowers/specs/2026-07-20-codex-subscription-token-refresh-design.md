# Codex subscription token refresh — design

**Date:** 2026-07-20
**Status:** Approved design (revised after external review), pending final spec review
**Area:** `back_end/domains/llm_providers`, `back_end/domains/runs`, `back_end/infrastructure`, Dockerfiles

## Problem

Users want to use their **Codex (ChatGPT) subscription** — much cheaper than the
OpenAI API — as an LLM provider in both self-hosted (local) and hosted (cloud)
OpenSweep. Today the subscription path is broken in any environment that relies
on a **stored** `auth.json` credential (mandatory for cloud):

1. The user pastes `~/.codex/auth.json` into the provider's Credential field.
   It is sealed and stored as an **immutable snapshot** in
   `LLMProvider.credential_secret`.
2. On every run, `runtime_env.build_runtime` writes that *same stored snapshot*
   to a worker-private `CODEX_HOME/.codex/auth.json` (`runtime_env.py:84-93`);
   `codex_turn_env` performs the write (`turn_cli.py:197-204`).
3. Codex's access token expires; codex refreshes using the snapshot's
   `refresh_token`.
4. OpenAI's OAuth uses **single-use rotating refresh tokens** — each refresh
   invalidates the previous refresh token. The snapshot's token was already
   consumed and rotated away (by the user's laptop codex, or by a prior OpenSweep
   run whose rotated token was never persisted). OpenAI rejects it → *"Your
   access token could not be refreshed. Please log out and sign in again."*

There is **no write-back path**: `provider_secret()` is read-only everywhere, so
a rotated token is never persisted back. The `last_refresh` the user sees in their
host `~/.codex/auth.json` is fresh because the *host* copy keeps winning the
rotation race; the stored OpenSweep copy is stale by construction.

The **bind-mount** path (no stored secret — codex owns the host `~/.codex`) works
and is out of scope for changes.

## Goals

- Codex subscription works reliably in **local and cloud**, including across
  ephemeral cloud containers (no persistent worker filesystem).
- Correct under **concurrency**: many runs share **one** provider row, so
  concurrent codex processes against one subscription is common.
- Use **OpenAI's supported** credential-maintenance pattern; do not take ownership
  of an undocumented OAuth integration.
- Custody the OAuth secret safely (sealed at rest, never logged, never plaintext
  in Redis).

## Non-goals

- Changing the bind-mount path.
- Solving the case where the **same** ChatGPT login is used simultaneously by
  OpenSweep *and* an external codex (laptop). Inherent to sharing one OAuth
  identity; mitigated by guidance (dedicated login for cloud), not code.
- Guaranteeing exactly-once rotation across arbitrary process termination — see
  "Irreducible crash window".

## Approach — A: let codex refresh, OpenSweep persists (serialized per subscription)

OpenAI's supported CI/CD guidance is: **let codex perform the refresh, persist the
resulting `auth.json`, and ensure only one serialized execution stream uses a given
credential copy at a time.** It explicitly says *not* to call the refresh endpoint
yourself. This design follows that exactly.

### Approaches considered and rejected

- **B — OpenSweep calls the OAuth endpoint directly** (hand codex a long-lived
  access token). Rejected: (a) unsupported and version-coupled to codex's OAuth
  request/response shape; (b) the generated `auth.json` still contains a refresh
  token and resolves as managed `chatgpt` auth, so codex can still **reactively
  refresh on an upstream 401** mid-turn and rotate the token out from under us —
  the ownership boundary is not actually enforced.
- **C — app-server external-token mode (`chatgptAuthTokens`) now.** This is the
  eventual target (see "Fast-follow"), but as an immediate step it combines too
  much foundational change: a substantial turn-runner rewrite (`codex exec` →
  app-server JSON-RPC) *and* dependency on an explicitly experimental protocol.
  Critically, external-token mode still requires the host to *produce* refreshed
  tokens on a 401 callback — so without a supported way to do that, it merely
  moves the unsupported refresh from turn start into the middle of the turn.

### Why A is safe where B was not

Because OpenSweep **serializes all turns that use a given stored subscription**,
exactly one codex process ever touches that credential copy at a time. Codex is
free to refresh whenever it needs to (proactively near expiry *or* reactively on a
401) — it does so with exclusive access, then OpenSweep persists whatever
`auth.json` codex leaves behind. No two codex processes can race on the rotating
token. Consequences:

- We do **not** parse the access-token JWT, compute margins, or proactively
  refresh. We compare the post-turn `auth.json` to the seeded copy and persist if
  it changed. This removes all coupling to codex's OAuth request/response shape
  (a concrete benefit over B).
- The earlier "token lifetime vs. turn timeout" invariant is gone. A codex
  mid-turn refresh is safe because the turn holds the credential exclusively.

### The cost, made explicit

Concurrent turns on **one** subscription serialize for the full turn duration.
**Different provider rows remain fully parallel.** This is an intentional
compatibility phase; the app-server fast-follow removes the whole-turn
serialization.

## Design

### 1. Lock boundary — the whole refresh transaction

The per-provider lock MUST cover the entire transaction, not just codex execution:

```
acquire per-subscription lock
  → read DB credential at revision R
  → seed worker-private CODEX_HOME/.codex/auth.json
  → run the complete codex turn (codex may refresh here, exclusively)
  → read the resulting auth.json
  → validate (parses, non-empty, account_id matches the seeded credential)
  → if changed: seal → CAS-persist at revision R → bump to R+1 → update caches
release lock
```

The lock is **not** released when codex exits but before write-back — the final
persistence is part of the refresh transaction.

### 2. Coordination — a Neo4j lease (globally effective, fail-closed by construction)

**Implementation refinement over the reviewed plan:** rather than a Redis lock
with a per-process fallback, the per-provider lease is a **Neo4j lock node**,
modeled on the existing `infrastructure/seeding/lock.py` (`MERGE` a
`CodexCredLock {id: <provider uid>}`, taken only when
`holder IS NULL OR expires_at < timestamp()`, self-expiring TTL). Coordination
therefore lives in the **same durable store as the credential**: if Neo4j is
unreachable no turn runs at all, so there is no split-brain window and no
local-lock fallback to get wrong — it is fail-closed by construction, strictly
stronger than "Redis normally, fail closed if Redis is down." A crashed holder's
lease self-expires after the TTL.

- Because a turn can run up to `TURN_TIMEOUT_SECONDS` (3600) while the lease TTL
  is short (120s), a **background task renews** the lease while the turn runs; the
  lease is released in a `finally` path (only by the holder — `WHERE holder =
  $token`).
- A queued turn waits up to a short, configurable budget
  (`OPENSWEEP_CODEX_LOCK_WAIT_SECONDS`, default 120s) for the subscription, then
  returns a **retryable 503** — a request never blocks for a whole long turn. The
  wait is cancellable.
- **Credential-revision fencing.** `LLMProvider.credential_revision` (monotonic).
  Persistence is a **conditional Cypher CAS**:

  ```cypher
  MATCH (p:LLMProvider {uid: $uid})
  WHERE coalesce(p.credential_revision, 0) = $expected_revision
  SET p.credential_secret = $sealed, p.credential_revision = $expected_revision + 1,
      p.needs_reauth = false, p.auth_state_uncertain = false
  RETURN p.credential_revision
  ```

  The revision represents the **credential**, not general provider-row updates. A
  CAS miss means the user re-pasted (which bumps the revision) or a peer persisted
  during the turn → the stale write-back is dropped, never overwriting the newer
  value.

### 3. Write-back rules

Write-back runs in a `finally`-style path after **success, failure, cancellation,
or timeout** — a failed turn may still have successfully refreshed the credential,
so write-back must not depend on turn success. Before persisting the on-disk
`auth.json`:

- It parses as JSON and is non-empty / not partially written.
- `tokens.account_id` still matches the seeded credential (guard against a swapped
  identity).
- **Lossless document:** keep the complete parsed document; replace only
  `tokens.id_token`, `tokens.access_token`, `tokens.refresh_token`, and
  `last_refresh` relative to the seed; preserve `auth_mode` and any unknown
  top-level / token-level fields (forward-compat with future codex versions).
- Seal via `infrastructure.secretbox` **before** the DB write.
- Persist via the revision CAS (§2).
- **Only if it changed** vs. the seeded copy (avoid needless revision churn).

### 4. Caching & security

- The blob stays sealed at rest (same as today; matches `github_app` L2, which
  seals). **The plaintext refresh token never enters Redis.** If a hot-path cache
  is used, cache either the already-sealed DB value or only non-secret fields
  (access-token/expiry/account-id/revision). The refresh token exists unsealed only
  transiently, in the process performing write-back.
- Tokens are never logged — logs carry only timestamps, revisions, and refresh
  outcomes. No token material in exceptions, HTTP traces, or telemetry.
- Cloud custodies a full ChatGPT refresh token (higher blast radius than an API
  key) — an accepted, documented tradeoff. Docs guidance: for cloud, use a
  **dedicated Codex login**, not one shared with a laptop running codex.

### 5. Failure taxonomy (provider state)

| Category | Examples | State |
|---|---|---|
| Permanent credential failure | reused / revoked / expired refresh token, account mismatch | `needs_reauth` |
| Transient authority failure | timeout, DNS, 429, 5xx | retryable error |
| Compatibility failure | unexpected `auth.json` schema, missing rotated token | operational alert |
| Coordination failure | no distributed lock available | retryable infra error |
| Uncertain | refresh outcome unknown (e.g. lost response after a timeout) | `auth_state_uncertain` |

`needs_reauth` is **never** set from an ambiguous timeout — the authority may have
consumed the token even though the response was lost. `auth_state_uncertain`
surfaces that distinctly; blindly retrying can worsen diagnosis. Add both
`needs_reauth` and `auth_state_uncertain` flags to `LLMProvider`, surface in the
provider DTO, and badge in the UI; clear on the next successful credential save.

Detection: since we don't call OAuth ourselves, "permanent failure" is inferred
from codex's own turn output/exit (codex reports the auth failure) plus the
post-turn `auth.json` state, not from an HTTP status we own.

### 6. Irreducible crash window (documented limitation)

Even under A: if codex rotates the token remotely and the OpenSweep process (or
container) dies **after** codex wrote the new `auth.json` but **before** OpenSweep
CAS-persists it, the only durable token is the consumed one → the user must
re-authenticate. External OAuth + our DB cannot share one transaction, so
exactly-once rotation is impossible without issuer idempotency/grace.

> **Refresh is concurrency-safe but not crash-atomic.** A process failure after
> codex's remote rotation and before durable persistence can require user
> reauthentication.

Mitigations: do no nonessential work between reading `auth.json` and committing;
have the DB write path ready before reading it back; commit first, then update
caches; alert on reused-token errors immediately following an interrupted turn.

### 7. Operational UX (make serialization visible)

- Queue turns per subscription; while waiting, report **"Waiting for another run
  using this Codex subscription."**
- Telemetry records lock-wait time and execution time **separately**.
- Support **cancellation while waiting** on the subscription lock.
- Optional configurable per-subscription queue depth limit.
- Different provider rows are unaffected and run fully in parallel.

### 8. Integration points (as built)

- **`runs/services/turn_service.py`**: `run_turn` loads the provider and wraps the
  turn in `async with codex_credential.codex_credential_txn(provider)`, delegating
  the body (workspace prep → subprocess spawn/stream → finalize) to a new
  `_run_turn_body` async generator via `contextlib.aclosing`. `aclosing`
  guarantees the codex subprocess is torn down **before** the transaction reads
  `auth.json` back. A 503 from the lease frees the reserved slot and propagates.
  The codex re-auth message is detected at finalize and turned into an actionable
  error + `mark_needs_reauth`.
- **`domains/llm_providers/services/codex_credential.py`** (new): the transaction
  — Neo4j per-provider lease (`CodexCredLock`) with renewal + cancellable wait,
  seed-baseline write under the lease, and the read-back + `decide_write_back` +
  revision-CAS persist. `is_codex_managed`, `mark_needs_reauth`.
- **`domains/llm_providers/services/codex_auth.py`** (new): pure parse/validate/
  compare helpers + `decide_write_back` (PERSIST / NOOP / UNCERTAIN /
  REJECT_ACCOUNT) + `looks_like_reauth`. No OAuth HTTP client — the stored
  document is codex's own file, persisted verbatim (lossless).
- **`runtime_env` / `turn_cli.codex_turn_env`**: unchanged seeding — it re-seeds
  `CODEX_HOME/.codex/auth.json` from `provider.credential_secret`, which the
  transaction refreshed to the current revision under the lease. Since turns are
  serialized per provider, the deterministic per-provider `CODEX_HOME` has a
  single writer at a time.
- **`models.py` / `schemas.py` / `llm_provider_service.py`**: `credential_revision`,
  `needs_reauth`, `auth_state_uncertain` on the node; the two flags surfaced in the
  DTO; a credential re-paste clears the flags and bumps the revision (invalidating
  any in-flight write-back CAS). Migration `m0009` initializes existing rows.

### 9. Version pinning

Pin `@openai/codex` to an exact version in `Dockerfile.prod` and `Dockerfile.dev`
(currently unpinned). A release checklist step re-validates the `auth.json`
document shape against fixtures from the pinned version before any bump. (We no
longer couple to the OAuth request/response, only to the on-disk document shape,
which §3's lossless handling already tolerates.)

## Fast-follow (committed milestone): app-server external-token mode

Target architecture, to remove whole-turn serialization:

```
parallel turn app-servers  (access tokens only)
        │ 401 refresh callback
        ▼
  short distributed refresh lock
        ▼
  codex-managed auth helper refreshes auth.json   ← NOT a direct OAuth call
        ▼
  CAS-persist rotated file
        ▼
  return new access token to the app-server
```

Codex never holds the refresh token; on a 401 the host supplies fresh tokens
within codex's callback window. Crucially, the callback fulfils the refresh via a
**codex-managed refresh helper**, not a direct OpenAI OAuth call — keeping us on
supported surface. This serializes only the brief refresh, not entire turns.
Requires a pinned codex, `experimentalApi`, and generated protocol schemas.

## Testing

Ordinary + adversarial:

- Two racing replicas: exactly one refresh stream; both observe the final token;
  DB written once.
- Lock expires after codex's rotation but before DB commit (lease renewal covers
  it; if it still lapses, CAS prevents a stale overwrite).
- Process terminates immediately after codex writes the new `auth.json` (crash
  window → `auth_state_uncertain` / reauth; asserted + alerted, not silently
  "healthy").
- User saves a new credential while a turn is in flight → in-flight write-back
  loses the CAS and does not clobber the new credential.
- Redis unavailable with two simulated replicas → fail closed (retryable), no
  double refresh.
- Write-back on failed / cancelled / timed-out turns still persists a valid
  rotated `auth.json`.
- `account_id` mismatch → write-back rejected.
- Redis contains no plaintext refresh token.
- Unknown top-level / token-level fields survive parse → merge → serialize.
- Stale-revision cache entry rejected; `needs_reauth` from an old revision cannot
  mark a newly-saved credential unhealthy.
- Ambiguous timeout → `auth_state_uncertain`, never `needs_reauth`.
- Cancellation while waiting on the subscription lock is honoured.
- No exception / trace / telemetry / structured-log field contains token material.

Follow existing patterns in `tests/test_codex_continuation.py`,
`tests/test_oauth_mcp.py`, and `github_app` tests.

## Rollout / repo notes

- Shared product code → **public `opensweep` repo** (this repo), merged into
  `opensweep-cloud` via the normal upstream merge. No `if cloud:` branches.
- No data migration for existing stored blobs: initialize `credential_revision`
  to 0; on the first serialized run the credential refreshes (or surfaces
  `needs_reauth`) and CAS-persists.

## v1 scope vs. deferred

**Built in this change:** the Neo4j per-subscription lease (+ renewal +
cancellable bounded wait → 503), seed-under-lease, read-back + revision-CAS
write-back on every exit path, the account-id / lossless / uncertain guards,
`needs_reauth` detection from codex output, the three `LLMProvider` fields + DTO
exposure + flag-clear-on-resave, migration `m0009`, codex version pin, and unit
tests for the pure helpers and the lease/CAS/write-back logic (fake `adb`).

**Deferred (follow-up):** the richer operational UX from §7 — a streamed
"waiting for another run using this Codex subscription" status event (the context
manager can't yield), separate lock-wait vs. execution telemetry, and a
configurable per-subscription queue-depth limit; the **front-end badge** for
`needs_reauth` / `auth_state_uncertain` (the API exposes both fields; the Vue
badge is not yet wired); and the **app-server external-token fast-follow**. None
affect correctness of the v1 mechanism.

## Decision record

Implement A as the initial production mechanism: serialize turns per stored Codex
subscription, allow codex to manage refresh and reactive retry, and durably
persist the resulting `auth.json` using globally effective locking,
credential-revision CAS, and sealed storage. This is an intentional compatibility
phase; the target is app-server external-token mode, where concurrent turns
receive access tokens only and reactive refresh is fulfilled through a
codex-managed refresh helper rather than direct OpenAI OAuth calls.
