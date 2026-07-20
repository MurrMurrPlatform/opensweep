"""Agents — the platform's single user-facing configuration concept.

An **Agent** is an org-scoped, versioned definition: a prompt, what it
produces, default effort/executor, tags. It absorbs the former AgentPrompt
library (all three flavors: agent bases, workflow stage defaults, variants)
and the former org agent overlays (per-org overrides with revisions).

- `provenance="system"` rows are platform-seeded and shared by every org
  (`org_uid=""`), identified by a stable `source_url`
  (`opensweep://agent/<key>`, `opensweep://workflow/<stage>`,
  `opensweep://library/<slug>`). Orgs customize them through override
  revisions, never by editing the shared row.
- `provenance="user"` rows belong to one org and carry that org's own
  prompts ("Nightly security sweep", …).
- `provenance="imported"` rows come from ECC re-imports; editing one turns
  it into a user row.

An **AgentRevision** is the append-only history. Rows with `org_uid=""`
snapshot edits to the shared/platform body; rows with a non-empty `org_uid`
ARE the org's override of a system agent (the absorbed overlay system):
the latest enabled revision per `(agent_uid, org_uid)` is the active
override, `mode="replace"` substitutes the agent's prompt, `mode="append"`
stacks under it as "## Organization guidance". A disabled or empty-body
head revision means "no override" (that is how deletes are represented —
history is never rewritten).

A **ScheduledAgent** binds an Agent to a repository with a trigger:
`""` (manual) | `"on-event"` (push webhook, path-scoped by `target.paths`)
| `"cron:<expr>"` (the beat scanner). It replaces the Investigation
concept; Runs it spawns point back via `Run.scheduled_agent_uid`.

Internally runs still carry a `playbook` — the machine discriminator that
selects sandbox mode, guards, and completion hooks. Users never pick a
playbook; they pick what an Agent *produces* and the registry maps it
(services/registry.py).
"""

from neomodel import (
    AsyncStructuredNode,
    BooleanProperty,
    DateTimeProperty,
    IntegerProperty,
    JSONProperty,
    StringProperty,
)

AGENT_PROVENANCES = {"system", "user", "imported"}

# What an Agent produces — the user-facing replacement for job_type AND for
# playbook-as-a-concept. registry.PRODUCES_TO_PLAYBOOK maps these onto the
# internal run playbooks.
PRODUCES = {
    "findings",        # audit-shaped: file evidenced Findings (ask playbook)
    "answer",          # conversational output (chat playbook)
    "documentation",   # doc/memory upkeep (document playbook)
    "doc-tree",        # system generate-docs: propose the page tree
    "analysis",        # system deep-scan: author a full Analysis
    "review-verdict",  # system PR review
    "verification",    # system skeptic pass
    "code-changes",    # write path (implement/fix/thread) — gated
}

# Generous body cap (carried over from the overlay system). Enforced in the
# service with a clear 422.
AGENT_PROMPT_MAX_BYTES = 32 * 1024

OVERRIDE_MODES = {"append", "replace"}

# Autonomy levels — how much permission a ScheduledAgent has to run on its
# own. (Formerly "compute_dial"; renamed because it gates permission, not
# compute — effort is the compute dial.)
AUTONOMY_LEVELS = {
    "disabled",
    "suggest",
    "ask-before-run",
    "auto-run-cheap",
    "auto-run-any",
}


class Agent(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)

    # "" = platform/system row shared by all orgs; else the owning org.
    org_uid = StringProperty(default="", index=True)

    title = StringProperty(required=True, index=True)
    description = StringProperty(default="")
    prompt = StringProperty(default="")  # markdown instructions body

    produces = StringProperty(default="findings", index=True)
    default_effort = StringProperty(default="normal")  # short | normal | deep | unlimited
    default_executor = StringProperty(default="")  # "" = provider-derived

    tags = JSONProperty(default=[])  # list[str]

    # system | user | imported
    provenance = StringProperty(default="user", index=True)
    # Stable identity for system rows (opensweep://agent/<key> …) and the
    # upstream URL for imported rows. "" on user rows.
    source_url = StringProperty(default="")
    source_commit = StringProperty(default="")

    # Seed provenance (system rows only). Hash of the platform-shipped
    # content this row was last seeded/synced from — lets a SYNC re-seed
    # tell an untouched system row from an admin-edited one, so shipped
    # improvements roll forward without clobbering edits.
    seed_checksum = StringProperty(default="")

    # Head revision of the shared/platform body (AgentRevision org_uid="").
    rev = IntegerProperty(default=0)

    enabled = BooleanProperty(default=True)

    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)


class AgentRevision(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)

    agent_uid = StringProperty(required=True, index=True)
    # "" = platform-body edit history; non-"" = that org's override of a
    # system agent (the absorbed overlay system).
    org_uid = StringProperty(default="", index=True)

    rev = IntegerProperty(required=True)  # monotonic per (agent_uid, org_uid)
    mode = StringProperty(default="replace")  # append | replace (override rows)
    body = StringProperty(default="")
    enabled = BooleanProperty(default=True)

    author_uid = StringProperty(default="")
    created_at = DateTimeProperty(default_now=True)


class ScheduledAgent(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)

    agent_uid = StringProperty(required=True, index=True)
    repository_uid = StringProperty(required=True, index=True)

    # Display override; "" = the bound agent's title.
    title = StringProperty(default="")

    # "" (manual) | "on-event" | "cron:<expression>" — schemas.parse_trigger.
    trigger = StringProperty(default="")

    # Scope: {"paths": [...], "doc_uids": [...], "limit": n}
    target = JSONProperty(default={})

    # "" = inherit the agent's default_effort.
    effort = StringProperty(default="")
    run_policy_uid = StringProperty(default="", index=True)

    # Autonomy (run-permission) level: disabled | suggest | ask-before-run |
    # auto-run-cheap | auto-run-any.
    autonomy = StringProperty(default="ask-before-run")

    enabled = BooleanProperty(default=True)

    # system (platform-seeded per repo) | user
    provenance = StringProperty(default="user", index=True)

    # Last time the cron scanner dispatched for this binding (UTC).
    last_scheduled_at = DateTimeProperty()

    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)
