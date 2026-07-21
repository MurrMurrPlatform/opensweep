"""Rename ScheduledAgent.compute_dial → autonomy.

The field gates run *permission* (disabled … auto-run-any), not compute —
effort is the compute dial — so it is renamed to `autonomy`. Values are
unchanged. DOWN reverses the rename losslessly.
"""

VERSION = 10
NAME = "scheduled-agent-autonomy"

SCHEMA_UP: list[str] = []
SCHEMA_DOWN: list[str] = []

UP: list[str] = [
    "MATCH (s:ScheduledAgent) WHERE s.compute_dial IS NOT NULL "
    "SET s.autonomy = s.compute_dial REMOVE s.compute_dial",
]
DOWN: list[str] = [
    "MATCH (s:ScheduledAgent) WHERE s.autonomy IS NOT NULL "
    "SET s.compute_dial = s.autonomy REMOVE s.autonomy",
]
