"""Drop constraints/indexes for the removed org-agent-overlay domain.

`OrgAgentOverlay` / `OrgAgentOverlayRevision` were replaced by per-org Agent
rows (agents-replace-investigations); the node classes no longer exist in
code, so the schema objects m0006 created are dead weight. No nodes were
ever migrated forward, so this is schema-only.

SCHEMA_DOWN recreates them so a deployment rollback to an older image (whose
bootstrap expects them) stays clean.
"""

VERSION = 9
NAME = "drop-overlay-constraints"

SCHEMA_UP: list[str] = [
    "DROP CONSTRAINT org_agent_overlay_uid IF EXISTS",
    "DROP CONSTRAINT org_agent_overlay_revision_uid IF EXISTS",
    "DROP INDEX org_agent_overlay_org IF EXISTS",
    "DROP INDEX org_agent_overlay_playbook IF EXISTS",
    "DROP INDEX org_agent_overlay_revision_org IF EXISTS",
    "DROP INDEX org_agent_overlay_revision_playbook IF EXISTS",
    "DROP INDEX org_agent_overlay_revision_overlay IF EXISTS",
]
SCHEMA_DOWN: list[str] = [
    "CREATE CONSTRAINT org_agent_overlay_uid IF NOT EXISTS "
    "FOR (n:OrgAgentOverlay) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT org_agent_overlay_revision_uid IF NOT EXISTS "
    "FOR (n:OrgAgentOverlayRevision) REQUIRE n.uid IS UNIQUE",
    "CREATE INDEX org_agent_overlay_org IF NOT EXISTS "
    "FOR (n:OrgAgentOverlay) ON (n.org_uid)",
    "CREATE INDEX org_agent_overlay_playbook IF NOT EXISTS "
    "FOR (n:OrgAgentOverlay) ON (n.playbook)",
    "CREATE INDEX org_agent_overlay_revision_org IF NOT EXISTS "
    "FOR (n:OrgAgentOverlayRevision) ON (n.org_uid)",
    "CREATE INDEX org_agent_overlay_revision_playbook IF NOT EXISTS "
    "FOR (n:OrgAgentOverlayRevision) ON (n.playbook)",
    "CREATE INDEX org_agent_overlay_revision_overlay IF NOT EXISTS "
    "FOR (n:OrgAgentOverlayRevision) ON (n.overlay_uid)",
]

UP: list[str] = []
DOWN: list[str] = []
