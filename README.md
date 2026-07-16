# OpenSweep

**A dashboard for your coding agents. Repo intelligence + AI dev-workflow platform.**

OpenSweep keeps a living Doc tree per repository, runs Investigations, records
Findings, and stamps what was Checked when (the discovery loop). It also runs
the delivery loop: Tickets with a human approval gate, implement/fix runs that
open draft PRs, SHA-bound review verdicts, and a per-PR convergence predicate
published as the `opensweep/converged` commit status. Interactive agent
Sessions (chat) are built in.

> **Discovery:** Sweep → doc-generation / audit runs → Docs + Memories + Findings → Checked stamps → re-check on push
> **Delivery:** Ticket → [approve] → Implement-run → PR → Review-run → Fix-run(s) → CONVERGED → [merge]

Exactly two human gates: approving a ticket, and merging the PR.

## Quickstart

Requirements: Docker (with Compose), ~4 GB free RAM, `git`.

```bash
git clone https://github.com/MurrMurrPlatform/opensweep.git
cd opensweep
./start.sh
```

That's it. First run builds images and bootstraps the bundled Zitadel auth
(a few minutes); re-runs are fast and idempotent. Then:

- **App:** http://127.0.0.1:5174 — log in as `qa@opensweep.localhost` / `OpenSweepQA-Password1!`
  (operator: `zitadel-admin@zitadel.localhost` / `Password1!`)
- **API:** http://127.0.0.1:8001 (`/health`, `/docs`)
- **Neo4j Browser:** http://127.0.0.1:7475 (`neo4j` / `koalapassword`)

All ports bind to `127.0.0.1`.

### First workflow

1. **Add an LLM provider** (Admin → LLM Providers); mark exactly one **Active**.
   Supported: Claude Code subscription CLI, OpenAI Codex CLI,
   OpenAI/Anthropic-compatible APIs, and local setups (MLX, LMStudio, Ollama, OpenCode).
2. **Connect GitHub**: paste a [fine-grained access token](https://github.com/settings/personal-access-tokens/new)
   (Contents + Pull requests read/write on the repos OpenSweep should see) in
   the welcome wizard or under Settings → GitHub — that's it. Even simpler:
   set `GITHUB_TOKEN` in `.env` before first login and it auto-connects.
   (Upgrade path: `scripts/github-app-setup.sh dev` provisions a GitHub App
   — one browser click — for auto-registering webhooks and short-lived
   per-repo credentials.)
3. Hit **Sweep this repo** — doc-generation and audit runs build the Doc tree and file Findings.
4. Triage Findings (fix now / ticket / waive), approve a Ticket, hit **Implement** —
   OpenSweep opens a draft PR and review-runs drive it to convergence.

## Core Concepts

| Concept | What it is |
|---|---|
| **Repository** | A GitHub repository. Agents work in disposable sandbox clones fetched from GitHub — nothing is mounted from the host. |
| **Doc** | Agent-written documentation node (path-slugged tree with `watch_paths`). The Doc tree is OpenSweep's concept layer; freshness is webhook-driven, and the tree exports to `AGENTS.md` via PR. |
| **Memory** | A small durable note an agent wrote for its future self (conventions, gotchas, decisions). |
| **Checked** | A freshness stamp: what was checked, when, at which revision, with what outcome. |
| **Investigation** | A question OpenSweep asks about a repository. Review/implement/fix runs reuse the same run machinery. |
| **Finding** | A bug, gap, improvement, risk, stale-doc note, missing-test note, or structural proposal. |
| **Ticket** | A unit of plannable work. Backlog → Todo is the human approval gate. |
| **PullRequest / Verdict / FindingResolution** | The convergence ledger: a webhook-synced PR mirror, SHA-bound review judgments, and the per-PR finding lifecycle. |
| **Session** | An interactive, turn-based chat with an agent CLI in a sandbox (WebSocket streaming, interrupt, transcripts). |
| **RunPolicy / MergePolicy** | Per-run cost ceilings; per-repo blocking thresholds and the fix-round bound. |

## Security model

- **Zitadel OIDC** is the only user auth, in every environment — the bundled
  dev stack ships it, and `./start.sh` configures it.
- **Webhooks** are HMAC-verified (`X-Hub-Signature-256`), idempotent per
  delivery id, and fail closed when no secret is configured.
- **Credentials never enter sandboxes**: agent environments are built from an
  explicit allowlist; agents call back with scoped per-run `osrt_` tokens; git
  pushes happen platform-side after the write gate. Stored credentials are
  encrypted at rest when `OPENSWEEP_SECRETS_KEY` is set.

## Verification

```bash
cd back_end && pytest
cd front_end && npm install && npm run type-check && npm run build
```

## OpenSweep Cloud

A managed OpenSweep Cloud is in the works — same product, zero ops.
Self-hosting stays free. Watch the repo or https://opensweep.ai for updates.

## License

OpenSweep is source-available under the [Elastic License 2.0](LICENSE):
free to use, modify, and self-host; you may not provide it to others as a
managed service. See `LICENSE` for the exact terms.
