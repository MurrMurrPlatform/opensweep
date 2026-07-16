"""Memory node — flat agent-written notes (KNOWLEDGE_V3_MEMORY.md).

Small facts an agent learned that the code cannot express. No status, no
versioning: a memory exists or is deleted, an update overwrites. Staleness
is computed at read time from the anchor Doc's code_changed_at —
never stored.
"""

from neomodel import (
    AsyncStructuredNode,
    DateTimeProperty,
    StringProperty,
)


class Memory(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)
    repository_uid = StringProperty(required=True, index=True)

    # Optional Doc uid the fact is about.
    anchor_uid = StringProperty(default="", index=True)

    title = StringProperty(required=True)  # one line — what search matches first
    body = StringProperty(default="")  # a paragraph, not a document

    # Internal dedup only — never exposed in DTOs.
    fingerprint = StringProperty(default="", index=True)

    source_run_uid = StringProperty(default="", index=True)

    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)
