"""RunPolicy node -- ceilings, routing, dry-run, repo budgets.

Bounds every tracking Run. Versioned so runs can explain which
policy was in force when they were dispatched.

Per-run money ceilings are gone: they were unmeasurable on subscription and
local executors and were never enforced. Money safety lives in the daily
aggregates (daily_repo_dollars et al.); per-run bounding is operational —
wall-time, tool turns, continuation passes, files touched.
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

    # Operational ceilings — apply to every executor.
    max_wall_seconds = IntegerProperty()
    max_tool_turns = IntegerProperty()
    max_files_touched = IntegerProperty()
    # Extra continuation passes per run. None = unbounded — the continuation
    # loop is then wall-limited only.
    max_continuation_passes = IntegerProperty()

    # Routing constraints
    cloud_allowed = BooleanProperty(default=False)
    local_only = BooleanProperty(default=False)
    allowed_executors = JSONProperty(default=[])  # empty = all allowed

    # Behavior
    dry_run = BooleanProperty(default=False)
    warn_at_pct = IntegerProperty(default=80)  # warn at 80% of any ceiling

    # Aggregate budgets (per repo, rolling daily)
    daily_repo_run_count = IntegerProperty()
    daily_repo_wall_seconds = IntegerProperty()
    daily_repo_dollars = FloatProperty()

    # Versioning -- runs reference the policy version in force.
    version = IntegerProperty(default=1)
    supersedes_uid = StringProperty(index=True)

    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)
