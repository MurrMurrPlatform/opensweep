"""Agent prompts library — editable, platform-wide.

A row per reusable agent prompt. Used by Ask (audit), Discover, Maintain,
and Verify flows. Seeded from github.com/affaan-m/ECC at install time;
user can edit / add / disable / re-import.
"""

from neomodel import (
    AsyncStructuredNode,
    BooleanProperty,
    DateTimeProperty,
    JSONProperty,
    StringProperty,
)


class AgentPrompt(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)

    title = StringProperty(required=True, index=True)
    description = StringProperty(default="")
    body = StringProperty(default="")  # markdown intent body

    default_job_type = StringProperty(default="audit", index=True)
    default_scope = StringProperty(default="repository")  # repository | paths
    default_effort = StringProperty(default="normal")

    tags = JSONProperty(default=[])  # list[str] — free-text labels ("security", "docs", …)

    # Origin
    source = StringProperty(default="user", index=True)  # platform | user | imported
    source_url = StringProperty(default="")
    source_commit = StringProperty(default="")

    # Seed provenance (platform rows only). Hash of the platform-shipped content
    # this row was last seeded/synced from. Lets a SYNC re-seed tell an
    # untouched platform prompt (current content still hashes to this) from one
    # a user edited in place (hashes differ) — so shipped-default improvements
    # roll forward without ever clobbering user edits. "" on user/imported rows
    # and on platform rows created before seed tracking existed.
    seed_checksum = StringProperty(default="")

    enabled = BooleanProperty(default=True)

    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)


AGENT_PROMPT_SOURCES = {"platform", "user", "imported"}
