"""Agents + ScheduledAgents — replace AgentPrompt/OrgAgentOverlay/Investigation.

Label swaps preserve uids, so every stored reference (Repository.workflow
JSON, Run.investigation_uid, comment subject uids, notification links)
stays valid without rewriting:

  1. AgentPrompt        →  Agent            (library rows; body→prompt,
                                             source→provenance, produces
                                             derived per system key)
  2. OrgAgentOverlayRevision → AgentRevision (org overrides of system
                                             agents; deleted overlays get a
                                             disabled tombstone revision so
                                             history alone never re-activates
                                             an override)
  3. Investigation survivors → ScheduledAgent (seeded "Keep docs current" /
                                             "Audit stale code" bind to
                                             system agents; user-created
                                             rows get a user Agent carrying
                                             their intent). All other
                                             Investigations were fan-out
                                             bookkeeping artifacts and are
                                             deleted.
  4. Run.investigation_uid → scheduled_agent_uid (dangling refs nulled);
     overlay provenance fields dropped.
  5. Repository.workflow JSON key "agent_prompt_uid" → "agent_uid" (the
     property is a serialized JSON string; uids were preserved by step 1).
  6. Comment.subject_type investigation → scheduled_agent where the subject
     survived.

seed_checksum is cleared on migrated system rows: the checksum format
changed with the field set, and the seeder's ""-checksum path adopts
untouched rows (current content == shipped) while preserving edited ones —
exactly the transition semantics we want.

DOWN restores a *working* pre-refactor state, not a byte-identical one:
deleted bookkeeping Investigations and overlay head nodes are not
resurrected (overlay heads are reconstructed from the max-rev revision).
"""

VERSION = 8
NAME = "agents-scheduled-agents"

SCHEMA_UP: list[str] = [
    "CREATE CONSTRAINT agent_uid IF NOT EXISTS FOR (n:Agent) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT agent_revision_uid IF NOT EXISTS "
    "FOR (n:AgentRevision) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT scheduled_agent_uid IF NOT EXISTS "
    "FOR (n:ScheduledAgent) REQUIRE n.uid IS UNIQUE",
    "CREATE INDEX agent_org IF NOT EXISTS FOR (n:Agent) ON (n.org_uid)",
    "CREATE INDEX agent_provenance IF NOT EXISTS FOR (n:Agent) ON (n.provenance)",
    "CREATE INDEX agent_revision_agent IF NOT EXISTS FOR (n:AgentRevision) ON (n.agent_uid)",
    "CREATE INDEX agent_revision_org IF NOT EXISTS FOR (n:AgentRevision) ON (n.org_uid)",
    "CREATE INDEX scheduled_agent_repo IF NOT EXISTS "
    "FOR (n:ScheduledAgent) ON (n.repository_uid)",
    "CREATE INDEX scheduled_agent_agent IF NOT EXISTS "
    "FOR (n:ScheduledAgent) ON (n.agent_uid)",
    "CREATE INDEX run_scheduled_agent IF NOT EXISTS FOR (n:Run) ON (n.scheduled_agent_uid)",
    "CREATE INDEX run_agent IF NOT EXISTS FOR (n:Run) ON (n.agent_uid)",
    # Old shapes
    "DROP CONSTRAINT investigation_uid IF EXISTS",
    "DROP INDEX investigation_repo IF EXISTS",
    "DROP INDEX investigation_job_type IF EXISTS",
    "DROP INDEX run_investigation IF EXISTS",
    "DROP CONSTRAINT org_agent_overlay_uid IF EXISTS",
    "DROP CONSTRAINT org_agent_overlay_revision_uid IF EXISTS",
    "DROP INDEX org_agent_overlay_org IF EXISTS",
    "DROP INDEX org_agent_overlay_playbook IF EXISTS",
    "DROP INDEX org_agent_overlay_revision_org IF EXISTS",
    "DROP INDEX org_agent_overlay_revision_playbook IF EXISTS",
    "DROP INDEX org_agent_overlay_revision_overlay IF EXISTS",
]

SCHEMA_DOWN: list[str] = [
    "DROP CONSTRAINT agent_uid IF EXISTS",
    "DROP CONSTRAINT agent_revision_uid IF EXISTS",
    "DROP CONSTRAINT scheduled_agent_uid IF EXISTS",
    "DROP INDEX agent_org IF EXISTS",
    "DROP INDEX agent_provenance IF EXISTS",
    "DROP INDEX agent_revision_agent IF EXISTS",
    "DROP INDEX agent_revision_org IF EXISTS",
    "DROP INDEX scheduled_agent_repo IF EXISTS",
    "DROP INDEX scheduled_agent_agent IF EXISTS",
    "DROP INDEX run_scheduled_agent IF EXISTS",
    "DROP INDEX run_agent IF EXISTS",
    "CREATE CONSTRAINT investigation_uid IF NOT EXISTS "
    "FOR (n:Investigation) REQUIRE n.uid IS UNIQUE",
    "CREATE INDEX investigation_repo IF NOT EXISTS "
    "FOR (n:Investigation) ON (n.repository_uid)",
    "CREATE INDEX run_investigation IF NOT EXISTS FOR (n:Run) ON (n.investigation_uid)",
    "CREATE CONSTRAINT org_agent_overlay_revision_uid IF NOT EXISTS "
    "FOR (n:OrgAgentOverlayRevision) REQUIRE n.uid IS UNIQUE",
]

UP: list[str] = [
    # ── 1. AgentPrompt → Agent (uid preserved) ──────────────────────────────
    "MATCH (p:AgentPrompt) "
    "SET p:Agent "
    "REMOVE p:AgentPrompt "
    "SET p.prompt = coalesce(p.body, ''), "
    "    p.org_uid = '', "
    "    p.rev = 0, "
    "    p.provenance = CASE coalesce(p.source, 'user') "
    "        WHEN 'platform' THEN 'system' "
    "        WHEN 'imported' THEN 'imported' "
    "        ELSE 'user' END, "
    "    p.produces = CASE "
    "        WHEN p.source_url = 'opensweep://agent/chat' THEN 'answer' "
    "        WHEN p.source_url IN ['opensweep://agent/review', 'opensweep://workflow/review'] "
    "            THEN 'review-verdict' "
    "        WHEN p.source_url IN ['opensweep://agent/verify', 'opensweep://workflow/verify'] "
    "            THEN 'verification' "
    "        WHEN p.source_url = 'opensweep://agent/deep-scan' THEN 'analysis' "
    "        WHEN p.source_url IN ['opensweep://agent/generate-docs', 'opensweep://workflow/discover'] "
    "            THEN 'doc-tree' "
    "        WHEN p.source_url STARTS WITH 'opensweep://library/' "
    "            AND coalesce(p.tags, '') CONTAINS '\"review\"' THEN 'review-verdict' "
    "        WHEN p.source_url STARTS WITH 'opensweep://library/' "
    "            AND coalesce(p.tags, '') CONTAINS '\"verify\"' THEN 'verification' "
    "        WHEN coalesce(p.default_job_type, '') = 'implement' THEN 'code-changes' "
    "        WHEN coalesce(p.default_job_type, '') = 'document' THEN 'documentation' "
    "        WHEN coalesce(p.default_job_type, '') = 'generate-docs' THEN 'doc-tree' "
    "        ELSE 'findings' END, "
    "    p.seed_checksum = '' "
    "REMOVE p.body, p.default_job_type, p.default_scope, p.source",
    # ── 2a. Overlay revisions → AgentRevision (joined on the system agent) ──
    "MATCH (rev:OrgAgentOverlayRevision) "
    "MATCH (a:Agent {provenance: 'system'}) "
    "WHERE a.source_url = 'opensweep://agent/' + rev.playbook "
    "CREATE (:AgentRevision {"
    "    uid: rev.uid, agent_uid: a.uid, org_uid: rev.org_uid, rev: rev.rev, "
    "    mode: coalesce(rev.mode, 'append'), body: coalesce(rev.body, ''), "
    "    enabled: coalesce(rev.enabled, true), "
    "    author_uid: coalesce(rev.author_uid, ''), created_at: rev.created_at})",
    # ── 2b. Deleted overlays: disabled tombstone so history alone never
    #        re-activates an override (old semantics: head deleted = none). ──
    "MATCH (rev:OrgAgentOverlayRevision) "
    "WHERE NOT EXISTS { "
    "    MATCH (:OrgAgentOverlay {org_uid: rev.org_uid, playbook: rev.playbook}) } "
    "WITH rev.org_uid AS org, rev.playbook AS pb, max(rev.rev) AS maxrev "
    "MATCH (a:Agent {provenance: 'system'}) "
    "WHERE a.source_url = 'opensweep://agent/' + pb "
    "CREATE (:AgentRevision {"
    "    uid: replace(randomUUID(), '-', ''), agent_uid: a.uid, org_uid: org, rev: maxrev + 1, "
    "    mode: 'append', body: '', enabled: false, author_uid: '', "
    "    created_at: timestamp() / 1000.0})",
    # ── 2c. Same tombstone rule for DISABLED overlay heads whose latest
    #        revision predates the disable (head state was authoritative). ──
    "MATCH (o:OrgAgentOverlay) WHERE coalesce(o.enabled, true) = false "
    "MATCH (a:Agent {provenance: 'system'}) "
    "WHERE a.source_url = 'opensweep://agent/' + o.playbook "
    "OPTIONAL MATCH (rev:OrgAgentOverlayRevision {org_uid: o.org_uid, playbook: o.playbook}) "
    "WITH o, a, max(coalesce(rev.rev, 0)) AS maxrev "
    "CREATE (:AgentRevision {"
    "    uid: replace(randomUUID(), '-', ''), agent_uid: a.uid, org_uid: o.org_uid, rev: maxrev + 1, "
    "    mode: coalesce(o.mode, 'append'), body: coalesce(o.body, ''), "
    "    enabled: false, author_uid: coalesce(o.updated_by, ''), "
    "    created_at: timestamp() / 1000.0})",
    "MATCH (rev:OrgAgentOverlayRevision) DELETE rev",
    "MATCH (o:OrgAgentOverlay) DELETE o",
    # ── 3a. The audit-stale system agent must exist before bindings can
    #        reference it (boot seeding runs AFTER migrations). Content
    #        matches the shipped seed spec so the first SYNC adopts it. ──
    "MERGE (a:Agent {provenance: 'system', source_url: 'opensweep://agent/audit-stale'}) "
    "ON CREATE SET "
    "    a.uid = replace(randomUUID(), '-', ''), "
    "    a.org_uid = '', "
    "    a.title = 'OpenSweep agent — Audit stale code', "
    "    a.description = 'Auto-selects the stalest / never-checked documentation pages "
    "and dispatches one scoped audit per page. Bind it to a repository with a cron "
    "trigger to keep coverage fresh.', "
    "    a.prompt = 'Automatically audit the documentation pages whose code has moved "
    "since they were last checked (never-checked pages first). Each due tick selects "
    "up to target.limit pages and dispatches one audit run scoped to each page\\'s "
    "watch_paths.', "
    "    a.produces = 'findings', "
    "    a.default_effort = 'normal', "
    "    a.default_executor = '', "
    "    a.tags = '[\"opensweep-agent-base\", \"audit-stale\"]', "
    "    a.source_commit = '', "
    "    a.seed_checksum = '', "
    "    a.rev = 0, "
    "    a.enabled = true, "
    "    a.created_at = timestamp() / 1000.0, "
    "    a.updated_at = timestamp() / 1000.0",
    # ── 3b. Seeded Investigations → ScheduledAgent bound to system agents ──
    "MATCH (i:Investigation {title: 'Keep docs current'}) "
    "MATCH (a:Agent {provenance: 'system', source_url: 'opensweep://agent/document'}) "
    "SET i:ScheduledAgent REMOVE i:Investigation "
    "SET i.agent_uid = a.uid, i.trigger = coalesce(i.schedule, ''), "
    "    i.enabled = true, i.provenance = 'system', i.effort = '', "
    "    i.run_policy_uid = coalesce(i.run_policy_uid, '') "
    "REMOVE i.intent, i.job_type, i.default_executor, i.default_mode, "
    "       i.schedule, i.description",
    "MATCH (i:Investigation {title: 'Audit stale code'}) "
    "MATCH (a:Agent {provenance: 'system', source_url: 'opensweep://agent/audit-stale'}) "
    "SET i:ScheduledAgent REMOVE i:Investigation "
    "SET i.agent_uid = a.uid, i.trigger = coalesce(i.schedule, ''), "
    "    i.enabled = true, i.provenance = 'system', i.effort = '', "
    "    i.run_policy_uid = coalesce(i.run_policy_uid, '') "
    "REMOVE i.intent, i.job_type, i.default_executor, i.default_mode, "
    "       i.schedule, i.description",
    # ── 3c. User survivors (a set schedule, or explicitly human-asked):
    #        a user Agent carries their intent; the binding keeps the
    #        schedule/dial/target. ──
    "MATCH (i:Investigation) "
    "WHERE coalesce(i.schedule, '') <> '' OR coalesce(i.provenance, '') = 'human-asked' "
    "OPTIONAL MATCH (r:Repository {uid: i.repository_uid}) "
    "CREATE (a:Agent {"
    "    uid: replace(randomUUID(), '-', ''), org_uid: coalesce(r.org_uid, ''), "
    "    title: CASE WHEN coalesce(i.title, '') <> '' THEN i.title "
    "        ELSE left(coalesce(i.intent, 'Agent'), 60) END, "
    "    description: coalesce(i.description, ''), "
    "    prompt: coalesce(i.intent, ''), "
    "    produces: CASE coalesce(i.job_type, '') "
    "        WHEN 'implement' THEN 'code-changes' "
    "        WHEN 'document' THEN 'documentation' "
    "        WHEN 'generate-docs' THEN 'doc-tree' "
    "        ELSE 'findings' END, "
    "    default_effort: coalesce(i.effort, 'normal'), "
    "    default_executor: coalesce(i.default_executor, ''), "
    "    tags: '[]', provenance: 'user', source_url: '', source_commit: '', "
    "    seed_checksum: '', rev: 1, enabled: true, "
    "    created_at: i.created_at, updated_at: i.updated_at}) "
    "SET i:ScheduledAgent REMOVE i:Investigation "
    "SET i.agent_uid = a.uid, i.trigger = coalesce(i.schedule, ''), "
    "    i.enabled = true, i.provenance = 'user', "
    "    i.effort = coalesce(i.effort, ''), "
    "    i.run_policy_uid = coalesce(i.run_policy_uid, '') "
    "REMOVE i.intent, i.job_type, i.default_executor, i.default_mode, "
    "       i.schedule, i.description",
    # ── 3d. Everything else was fan-out bookkeeping — drop it. ──
    "MATCH (i:Investigation) DETACH DELETE i",
    # ── 4. Run rewiring ─────────────────────────────────────────────────────
    "MATCH (r:Run) WHERE r.investigation_uid IS NOT NULL "
    "SET r.scheduled_agent_uid = r.investigation_uid "
    "REMOVE r.investigation_uid",
    "MATCH (r:Run) WHERE coalesce(r.scheduled_agent_uid, '') <> '' "
    "AND NOT EXISTS { MATCH (:ScheduledAgent {uid: r.scheduled_agent_uid}) } "
    "SET r.scheduled_agent_uid = ''",
    "MATCH (r:Run) REMOVE r.overlay_uid, r.overlay_rev",
    # ── 5. Workflow config key rename (serialized JSON string property) ─────
    "MATCH (r:Repository) WHERE coalesce(r.workflow, '') CONTAINS '\"agent_prompt_uid\"' "
    "SET r.workflow = replace(r.workflow, '\"agent_prompt_uid\"', '\"agent_uid\"')",
    # ── 6. Comment subjects (only where the target survived the swap) ───────
    "MATCH (c:Comment) WHERE c.subject_type = 'investigation' "
    "AND EXISTS { MATCH (:ScheduledAgent {uid: c.subject_uid}) } "
    "SET c.subject_type = 'scheduled_agent'",
]

DOWN: list[str] = [
    # Comments back
    "MATCH (c:Comment) WHERE c.subject_type = 'scheduled_agent' "
    "SET c.subject_type = 'investigation'",
    # Workflow key back
    "MATCH (r:Repository) WHERE coalesce(r.workflow, '') CONTAINS '\"agent_uid\"' "
    "SET r.workflow = replace(r.workflow, '\"agent_uid\"', '\"agent_prompt_uid\"')",
    # Run fields back
    "MATCH (r:Run) WHERE r.scheduled_agent_uid IS NOT NULL "
    "SET r.investigation_uid = r.scheduled_agent_uid "
    "REMOVE r.scheduled_agent_uid",
    # ScheduledAgent → Investigation (agent prompt re-inlined as intent)
    "MATCH (s:ScheduledAgent) "
    "OPTIONAL MATCH (a:Agent {uid: s.agent_uid}) "
    "SET s:Investigation REMOVE s:ScheduledAgent "
    "SET s.schedule = coalesce(s.trigger, ''), "
    "    s.intent = coalesce(a.prompt, ''), "
    "    s.job_type = CASE coalesce(a.produces, 'findings') "
    "        WHEN 'code-changes' THEN 'implement' "
    "        WHEN 'documentation' THEN 'document' "
    "        WHEN 'doc-tree' THEN 'generate-docs' "
    "        ELSE 'audit' END, "
    "    s.default_executor = 'internal_llm', "
    "    s.default_mode = 'analyze_only', "
    "    s.provenance = CASE coalesce(s.provenance, 'user') "
    "        WHEN 'system' THEN 'template' ELSE 'human-asked' END, "
    "    s.effort = CASE WHEN coalesce(s.effort, '') = '' THEN 'normal' ELSE s.effort END "
    "REMOVE s.trigger, s.agent_uid",
    # Org override revisions back (playbook recovered from the agent key)
    "MATCH (rev:AgentRevision) WHERE coalesce(rev.org_uid, '') <> '' "
    "MATCH (a:Agent {uid: rev.agent_uid}) "
    "WHERE a.source_url STARTS WITH 'opensweep://agent/' "
    "CREATE (:OrgAgentOverlayRevision {"
    "    uid: rev.uid, overlay_uid: '', org_uid: rev.org_uid, "
    "    playbook: replace(a.source_url, 'opensweep://agent/', ''), "
    "    rev: rev.rev, mode: rev.mode, body: rev.body, enabled: rev.enabled, "
    "    author_uid: rev.author_uid, created_at: rev.created_at})",
    "MATCH (rev:AgentRevision) DELETE rev",
    # User agents created by UP have no AgentPrompt ancestor — drop them;
    # library rows swap back.
    "MATCH (a:Agent) WHERE coalesce(a.source_url, '') = '' "
    "AND coalesce(a.provenance, '') = 'user' AND coalesce(a.seed_checksum, '') = '' "
    "AND NOT EXISTS { MATCH (:ScheduledAgent {agent_uid: a.uid}) } "
    "DETACH DELETE a",
    "MATCH (a:Agent) "
    "SET a:AgentPrompt REMOVE a:Agent "
    "SET a.body = coalesce(a.prompt, ''), "
    "    a.source = CASE coalesce(a.provenance, 'user') "
    "        WHEN 'system' THEN 'platform' "
    "        WHEN 'imported' THEN 'imported' ELSE 'user' END, "
    "    a.default_scope = 'repository', "
    "    a.default_job_type = CASE coalesce(a.produces, 'findings') "
    "        WHEN 'code-changes' THEN 'implement' "
    "        WHEN 'documentation' THEN 'document' "
    "        WHEN 'doc-tree' THEN 'generate-docs' "
    "        ELSE 'audit' END "
    "REMOVE a.prompt, a.produces, a.provenance, a.org_uid, a.rev",
]
