"""Workspace (sandbox) node — the git clone an agent Run works in.

PLATFORM_V3_DESIGN.md §7: the sandbox is infrastructure, not a user-facing
concept. A Run owns at most one live sandbox (Run.sandbox_uid) and records a
workspace_spec to recreate it after retention expiry. The V2 Execution and
ExecutionEnvironment entities were deleted in V3 (§1); per-repo execution
settings live on the Repository.
"""

from neomodel import (
    AsyncStructuredNode,
    DateTimeProperty,
    StringProperty,
)


class Sandbox(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)
    repository_uid = StringProperty(required=True, index=True)
    host_path = StringProperty(required=True)        # path the user sees on host
    container_path = StringProperty(required=True)   # path the backend uses
    source_branch = StringProperty(default="main")
    sandbox_branch = StringProperty(default="opensweep/work")
    # discovery (read-only inspection clone) | write (implement/fix runs —
    # the agent commits inside; the platform validates and pushes).
    purpose = StringProperty(default="discovery", index=True)
    status = StringProperty(default="preparing")
    # preparing | ready | failed | destroyed
    created_at = DateTimeProperty(default_now=True)
    destroyed_at = DateTimeProperty()
    # Sliding retention (V3 §7): pushed out on every turn; the cleanup beat
    # destroys the clone once this passes.
    cleanup_after = DateTimeProperty()
    error = StringProperty(default="")
