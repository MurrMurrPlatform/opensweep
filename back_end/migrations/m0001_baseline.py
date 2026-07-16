"""Baseline — marks the pre-framework graph shape as version 1.

Everything that exists today (constraints via neomodel_bootstrap, seeded
defaults via the startup seeders) is the baseline; this migration only
plants the version marker. Existing databases and fresh ones both apply it
as a no-op, so from here on every shape change is a numbered migration.
"""

VERSION = 1
NAME = "baseline"

SCHEMA_UP: list[str] = []
SCHEMA_DOWN: list[str] = []
UP: list[str] = []
DOWN: list[str] = []
