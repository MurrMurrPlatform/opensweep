# Schema migrations

Versioned, reversible migrations for the Neo4j graph. Runner:
`infrastructure/migration_runner.py`. Applied automatically at backend
startup; a failure **aborts the boot** so the deploy goes unhealthy instead
of serving a half-migrated graph.

## Adding a migration

1. Create `m<NNNN>_<slug>.py` with the next contiguous version:

```python
"""Split Run.usage.provider_* into first-class properties."""

VERSION = 2
NAME = "run-provider-fields"

# Schema statements run auto-commit (Neo4j can't mix them with data writes)
# — every one MUST be idempotent (IF NOT EXISTS / IF EXISTS).
SCHEMA_UP = [
    "CREATE INDEX run_provider IF NOT EXISTS FOR (n:Run) ON (n.provider_kind)",
]
SCHEMA_DOWN = [
    "DROP INDEX run_provider IF EXISTS",
]

# Data statements run in ONE transaction together with the version marker —
# any failure rolls the whole migration back atomically.
UP = [
    "MATCH (r:Run) WHERE r.provider_kind IS NULL SET r.provider_kind = coalesce(r.usage_provider_kind, '')",
]
DOWN = [
    "MATCH (r:Run) REMOVE r.provider_kind",
]
```

2. Rules:
   - **Pure Cypher only.** DOWN statements are stored in the database on
     apply, so an *older* image (which doesn't ship your file) can revert
     them after a deployment rollback.
   - **Applied migrations are immutable.** The runner checksums every file;
     editing an applied migration fails the next boot. Add a new one.
   - **Always write DOWN.** A migration without one is applied as
     *irreversible*: deployment rollback past it will refuse to boot until a
     human intervenes. Only ship that when a revert is truly meaningless,
     and say so in the docstring.
   - Model/property additions usually need **no** migration (Neo4j is
     schemaless; neomodel defaults cover new properties). Write one when you
     rename/move/backfill data, change constraints/indexes, or relabel nodes.
   - Seeded *values* stay in the seeders (see `ensure_system_default`'s
     legacy-value migration pattern); migrations own *shape*.

## Operations

```bash
docker exec opensweep_backend python -m scripts.migrate status
docker exec opensweep_backend python -m scripts.migrate up          # what startup does
docker exec opensweep_backend python -m scripts.migrate down --to 3 # manual revert
```

## Deployment rollback (Coolify)

- **Failed deploy:** the new image's boot aborts on a migration error; the
  failing migration's transaction already rolled back, so the database is
  still at the previous version and the previous deployment keeps serving.
- **Rolling back a successful deploy:** redeploy the previous image as
  usual. On boot it finds the database *ahead* of its code and (with
  `OPENSWEEP_MIGRATIONS_AUTO_ROLLBACK=true`, the default) reverts the newer
  migrations using their stored DOWN statements, newest first, each
  transactionally. If one of them was irreversible, the boot fails with
  instructions instead — nothing is guessed.
- With `OPENSWEEP_MIGRATIONS_AUTO_ROLLBACK=false`, run
  `python -m scripts.migrate down --to <target>` from the *newer* image
  before triggering the rollback.

The runner serializes concurrent boots via a lease lock node
(`:SchemaMigrationLock`, 15 min expiry), so multiple replicas or a
simultaneous CLI run can't double-apply.
