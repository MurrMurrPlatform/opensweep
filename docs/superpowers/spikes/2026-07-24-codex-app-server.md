# Spike: Codex app-server concurrency on one ChatGPT subscription

**Date:** 2026-07-24 · **codex-cli:** 0.145.0 · **Driver:** `codex_app_server_spike.py` (this dir)
**Gate for:** Phase 4 of `plans/2026-07-24-tenant-safety-and-codex-app-server.md`

## Question
Can ONE `codex app-server` process run multiple concurrent threads (each its own
`cwd`) off ONE ChatGPT-subscription `auth.json`, streaming both, with central
token refresh and no rotation race — i.e. does the app-server give
subscription users real concurrency without the per-run credential race?

## Method
Throwaway copy of a real ChatGPT-subscription `auth.json` into a temp
`CODEX_HOME` (real `~/.codex` untouched). Spawned `codex app-server --stdio`
(newline-delimited JSON-RPC 2.0). Handshake `initialize` → `initialized`, then
two `thread/start` (distinct temp `cwd`, `sandbox: read-only`,
`approvalPolicy: never`), then **both** `turn/start` fired before awaiting either
(true in-process concurrency). Watched the JSONL notification stream.

## Result: PASS
- **Concurrency:** both threads started and both turns ran at once in one process;
  both reached `turn/completed` (2/2). Interleaved streaming confirmed.
- **Streaming:** native `item/agentMessage/delta` per thread (replaces our
  `exec --json` stdout parsing / `_codex_delta_feeder`).
- **One credential, no race:** both threads shared the single in-process
  `auth.json`. **0 errors, 0 "could not be refreshed".** access_token unchanged
  this run (not near expiry) — refresh is central by construction when needed.
- **Verdict line:** `PASS — concurrent threads, one credential, no rotation race`.

## Protocol facts captured (for the Phase-4 client)
- Transport: **stdio = JSONL** (one JSON-RPC object per line). unix/ws = websocket
  frames (ws flagged *experimental & unsupported* by OpenAI — prefer stdio, or a
  local unix socket, per app-server process).
- Handshake: `initialize {clientInfo:{name,version}, capabilities:{experimentalApi:true}}`
  → result `{userAgent, codexHome, platformFamily, platformOs}` → notify `initialized`.
- `thread/start {cwd, sandbox, approvalPolicy, model?}` → `{thread:{id,…}}` + `thread/started`.
- `turn/start {threadId, input:[{type:"text",text}], model?}` → `{turn:{id,status}}` +
  stream `turn/started` · `item/started` · `item/agentMessage/delta` · `item/completed`
  · `thread/tokenUsage/updated` · `turn/completed`.
- Also emitted: **`account/rateLimits/updated`** (→ per-subscription admission/throttle),
  **`mcpServer/startupStatus/updated`** per thread (→ where OpenSweep's platform +
  code-graph MCP servers attach), `remoteControl/status/changed`.
- SandboxMode enum: `read-only | workspace-write | danger-full-access`
  (OpenSweep uses `danger-full-access`, container is the sandbox).

## Best-practice context (OpenAI docs)
- ChatGPT-subscription auth: **"one auth.json per runner, no concurrent sharing"**;
  **"if you rewrite the file from the original secret on every run, you throw away
  the refreshed tokens codex just wrote."** The app-server IS that single runner
  (one process multiplexes threads) → concurrency without violating the rule.
  This matches the lease + write-back we already shipped.
- OpenAI recommends API keys for automation (self-serving — API billing). Product
  decision: keep **both auth paths first-class**; subscriptions ("no API bill")
  get concurrency via app-server; API keys stay available and are parallel by
  construction.
- `access-token-only broker` (old Phase-4 Model B): **DROPPED** — it would break
  codex's own auto-refresh; the app-server owning refresh is the supported path.

## Decision → Phase 4 GO (app-server-per-subscription)
Model **A**: one long-lived `codex app-server` per subscription (per org — a
subscription is single-tenant, so isolation stays structural), multiplexing
concurrent threads, each thread pinned to a run's sandbox clone as `cwd` with
`sandbox: danger-full-access`. Plugs in behind the `codex_cli` seam. Retires the
per-run lease-serialization, the `exec --json` parsing, and the continuation
hack (native `thread/resume`). API-key providers remain a separate,
parallel-by-construction path. Next: author Phase-4 task steps from the protocol
facts above (stdio JSONL client, thread/turn lifecycle, MCP attach via
`mcpServer` config, admission control off `account/rateLimits`).

## Open items to verify during build
- Force a near-expiry refresh to observe central rotation write-back (didn't
  trigger here). Confirm the app-server persists rotated tokens to its CODEX_HOME
  `auth.json` (then OpenSweep CAS-persists to the sealed credential, as today).
- Pin codex version; `app-server` protocol is experimental (regen schema per bump).
- Map OpenSweep's per-run MCP servers (opensweep platform + code-graph) into
  `thread/start` config / `mcpServer` surface.
