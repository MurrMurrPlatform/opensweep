# OpenSweep — agent notes

Repo intelligence + AI dev-workflow platform. Start with `README.md`.

## Two-repo layout (open core)

OpenSweep is developed across two repos that share git history:

- **`opensweep`** (public, source-available) — the product. **All shared and
  product development happens here.**
- **`opensweep-cloud`** (private) — a fork carrying a purely *additive*
  overlay: deployment infra, internal docs, ops tooling, and cloud-only
  features. It has an `upstream` remote pointing at the public repo
  (push disabled) and syncs with `git fetch upstream && git merge upstream/main`.

Rules that keep the merge conflict-free:

1. Never edit shared product code in the cloud repo — commit it here, then
   merge it into cloud. If shared changes were accidentally made in cloud,
   cherry-pick them here first.
2. Cloud-only features (billing, entitlements, …) live in the cloud repo as
   additive modules in their own paths. When such a feature needs to touch
   shared code, add the extension point *here* (with a no-op or
   allow-everything default) and implement it in cloud — never `if cloud:`
   branches in shared files.
3. `CLAUDE.md` and `README.md` are upstream-owned: the cloud repo keeps them
   byte-identical to this repo. Cloud-specific instructions live in `CLOUD.md`.

**If a `CLOUD.md` file exists in this checkout, you are working in the cloud
overlay repo — read it before making changes.**

## Dev auth (required reading for browser tooling)

Zitadel OIDC is the ONLY user auth, in every environment — there is no
no-auth dev mode. Backend refuses to boot without `ZITADEL_ISSUER`
(`back_end/infrastructure/production_guards.py`); frontend renders a config
screen without `VITE_ZITADEL_*` (`front_end/src/main.ts`).

- Bring the stack up: `docker compose up -d`, then **once**:
  `scripts/zitadel-dev-setup.sh` (configures the bundled Zitadel at
  http://localhost:8300, seeds users, writes `.env`, restarts app containers).
- Frontend: http://127.0.0.1:5174 · Backend: http://127.0.0.1:8001

To access the app through a browser (headless QA, MCP browser agents), sign
in through the real Zitadel login form — dev has no CAPTCHA/MFA, and the
session cookie persists in the browser profile, so log in once per session:

- **QA user (use this):** `qa@opensweep.localhost` / `OpenSweepQA-Password1!` —
  a regular tenant user with its own org; catches real permission bugs.
- Operator (platform admin, only when testing admin surfaces):
  `zitadel-admin@zitadel.localhost` / `Password1!`

For non-browser API access, use `OPENSWEEP_AUTH_TOKEN` from `.env`
(`Authorization: Bearer …` or `X-OpenSweep-Auth`); executor MCP clients use
their per-run `osrt_…` token. These are service credentials — they do not
log a user in.

## Testing across both repos

The public and cloud dev stacks use identical container names (`opensweep_*`)
and host ports (backend 8001, frontend 5174, Neo4j 7475/7688, Redis 6380), so
**only one stack can run at a time** — `docker compose down` in one repo
before `docker compose up` in the other. Shared features are tested here
first, then re-tested in cloud after the upstream merge (that run exercises
shared code + overlay together, which is what ships).
