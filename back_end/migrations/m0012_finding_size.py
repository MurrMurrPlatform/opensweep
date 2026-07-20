"""Rename Finding.effort → size.

The field is a fix-size estimate (trivial … large), not the run effort tier
(short/normal/deep/unlimited) — so it is renamed to `size` to stop the
collision. Values are unchanged. DOWN reverses the rename losslessly.
"""

VERSION = 12
NAME = "finding-size"

SCHEMA_UP: list[str] = []
SCHEMA_DOWN: list[str] = []

UP: list[str] = [
    "MATCH (f:Finding) WHERE f.effort IS NOT NULL "
    "SET f.size = f.effort REMOVE f.effort",
]
DOWN: list[str] = [
    "MATCH (f:Finding) WHERE f.size IS NOT NULL "
    "SET f.effort = f.size REMOVE f.size",
]
