"""Versioned Neo4j migrations.

One module per migration, named ``m<NNNN>_<slug>.py``. Versions are
contiguous integers starting at 1 — a gap or duplicate fails loudly at
startup, so merge conflicts surface as boot errors, not silent skips.

Module contract (all lists are plain Cypher strings — see README.md):

    VERSION = 2
    NAME = "add-run-cost-index"
    # Schema statements (CREATE/DROP CONSTRAINT|INDEX). Run OUTSIDE the
    # transaction (Neo4j forbids mixing them with data writes) — every one
    # MUST be idempotent (IF NOT EXISTS / IF EXISTS).
    SCHEMA_UP: list[str] = []
    SCHEMA_DOWN: list[str] = []
    # Data statements. Run in ONE transaction together with the version
    # bookkeeping — a failure rolls the whole migration back atomically.
    UP: list[str] = []
    DOWN: list[str] = []

Pure Cypher only, no Python callables: the DOWN/SCHEMA_DOWN statements are
stored in the database when a migration is applied, so an OLDER deployment
(which doesn't ship this file) can still revert it when Coolify rolls back.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType


def migration_modules() -> list[ModuleType]:
    """Import every m*.py module in this package, sorted by filename."""
    modules: list[ModuleType] = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.name.startswith("m"):
            modules.append(importlib.import_module(f"{__name__}.{info.name}"))
    return modules
