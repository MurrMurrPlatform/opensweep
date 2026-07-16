"""Org agent overlays — uid uniqueness + org/playbook lookup indexes.

`OrgAgentOverlay` is resolved on EVERY playbook dispatch by
(org_uid, playbook), and `OrgAgentOverlayRevision` is listed by the same key
for the history drawer, so both get lookup indexes alongside the standard
uid uniqueness constraints. Data is created by the application; DOWN only
drops the schema objects (never the nodes), so a rollback is lossless.
"""

VERSION = 6
NAME = "org-agent-overlays"

SCHEMA_UP: list[str] = [
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
SCHEMA_DOWN: list[str] = [
    "DROP CONSTRAINT org_agent_overlay_uid IF EXISTS",
    "DROP CONSTRAINT org_agent_overlay_revision_uid IF EXISTS",
    "DROP INDEX org_agent_overlay_org IF EXISTS",
    "DROP INDEX org_agent_overlay_playbook IF EXISTS",
    "DROP INDEX org_agent_overlay_revision_org IF EXISTS",
    "DROP INDEX org_agent_overlay_revision_playbook IF EXISTS",
    "DROP INDEX org_agent_overlay_revision_overlay IF EXISTS",
]

UP: list[str] = []
DOWN: list[str] = []
