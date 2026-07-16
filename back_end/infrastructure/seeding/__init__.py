"""Unified data seeding for OpenSweep.

`run_seeders` is the single entry point; the registry is the single source of
truth for what a fresh install needs. See registry.py for the group model and
SeedMode (base.py) for how re-seeds treat existing rows.
"""

from __future__ import annotations

from infrastructure.seeding.base import SeedMode, SeedResult, content_hash
from infrastructure.seeding.registry import (
    DEV,
    PLATFORM,
    SEEDERS,
    Seeder,
    run_seeders,
    summarize,
)

__all__ = [
    "SeedMode",
    "SeedResult",
    "content_hash",
    "run_seeders",
    "summarize",
    "SEEDERS",
    "Seeder",
    "PLATFORM",
    "DEV",
]
