"""Drop never-enforced RunPolicy cost/dormant ceilings + Agent.default_executor.

Per-run money ceilings (max_dollars / max_tokens) were unmeasurable on
subscription and local executors and were never enforced — money safety
lives in the daily aggregates. max_test_seconds / max_patch_lines were
dormant pre-v1 storage; on_exceed never had a runtime consumer (ceilings
are warnings-only). Agent.default_executor was never consulted — the
executor is provider-derived at dispatch.

DOWN is intentionally empty: this is a pure value drop, boot-safe on
rollback — older models default every removed property to None/"" and the
fields were never enforced, so there is nothing meaningful to restore.
"""

VERSION = 11
NAME = "run-policy-slim"

SCHEMA_UP: list[str] = []
SCHEMA_DOWN: list[str] = []

UP: list[str] = [
    "MATCH (p:RunPolicy) "
    "REMOVE p.max_dollars, p.max_tokens, p.max_test_seconds, p.max_patch_lines, p.on_exceed",
    "MATCH (a:Agent) REMOVE a.default_executor",
]
DOWN: list[str] = []
