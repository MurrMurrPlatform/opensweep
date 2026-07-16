"""RunPolicy node -- ceilings, routing, dry-run, repo budgets.

Bounds every tracking Run. Versioned so runs can explain which
policy was in force when they were dispatched.

Cost ceilings (max_tokens, max_dollars) only apply where the executor
exposes exact pricing -- primarily internal_llm with an API provider. For
subscription executors (claude_code / codex) the operational ceilings
(wall-time, tool turns, files touched) are the safety net.
"""

from neomodel import (
    AsyncStructuredNode,
    BooleanProperty,
    DateTimeProperty,
    FloatProperty,
    IntegerProperty,
    JSONProperty,
    StringProperty,
)


class RunPolicy(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)
    name = StringProperty(default="")
    description = StringProperty(default="")

    # Cost ceilings — apply where measurable.
    max_tokens = IntegerProperty()
    max_dollars = FloatProperty()

    # Operational ceilings — apply to every executor.
    max_wall_seconds = IntegerProperty()
    max_tool_turns = IntegerProperty()
    max_files_touched = IntegerProperty()
    # Dormant storage from pre-v1 source-change experiments. Kept only so old
    # databases continue to load; it is not exposed by v1 APIs.
    max_patch_lines = IntegerProperty()
    max_test_seconds = IntegerProperty()

    # Routing constraints
    cloud_allowed = BooleanProperty(default=False)
    local_only = BooleanProperty(default=False)
    allowed_executors = JSONProperty(default=[])  # empty = all allowed

    # Behavior
    dry_run = BooleanProperty(default=False)
    warn_at_pct = IntegerProperty(default=80)  # warn at 80% of any ceiling
    on_exceed = StringProperty(default="abort")  # abort | pause_for_approval

    # Aggregate budgets (per repo, rolling daily)
    daily_repo_run_count = IntegerProperty()
    daily_repo_wall_seconds = IntegerProperty()
    daily_repo_dollars = FloatProperty()

    # Versioning -- runs reference the policy version in force.
    version = IntegerProperty(default=1)
    supersedes_uid = StringProperty(index=True)

    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)


ON_EXCEED_VALUES = {"abort", "pause_for_approval"}
