"""Pure-Python tests for the migration planner.

DB execution (apply/revert/lock) is exercised by the smoke flow against a
live Neo4j; here we pin the planning invariants every boot relies on:
contiguity, checksum immutability, and the ahead-of-code (deployment
rollback) diff.
"""

import pytest

from infrastructure.migration_runner import (
    AppliedRecord,
    MigrationDef,
    MigrationError,
    build_plan,
    load_definitions,
)


class _Mod:
    def __init__(self, version, name, **kw):
        self.VERSION = version
        self.NAME = name
        self.SCHEMA_UP = kw.get("schema_up", [])
        self.SCHEMA_DOWN = kw.get("schema_down", [])
        self.UP = kw.get("up", [])
        self.DOWN = kw.get("down", [])


def _applied(mig: MigrationDef) -> AppliedRecord:
    return AppliedRecord(
        version=mig.version,
        name=mig.name,
        checksum=mig.checksum,
        down=mig.down,
        schema_down=mig.schema_down,
        reversible=mig.reversible,
    )


def test_load_definitions_requires_contiguous_versions():
    ok = load_definitions([_Mod(2, "b"), _Mod(1, "a")])
    assert [d.version for d in ok] == [1, 2]

    with pytest.raises(MigrationError, match="contiguous"):
        load_definitions([_Mod(1, "a"), _Mod(3, "c")])
    with pytest.raises(MigrationError, match="contiguous"):
        load_definitions([_Mod(1, "a"), _Mod(1, "dup")])
    with pytest.raises(MigrationError, match="contiguous"):
        load_definitions([_Mod(2, "starts-at-two")])


def test_checksum_covers_every_statement_list():
    base = MigrationDef(version=1, name="a", up=("MATCH (n) SET n.x = 1",))
    assert base.checksum == MigrationDef(version=1, name="a", up=("MATCH (n) SET n.x = 1",)).checksum
    for variant in [
        MigrationDef(version=1, name="a", up=("MATCH (n) SET n.x = 2",)),
        MigrationDef(version=1, name="a", down=("MATCH (n) REMOVE n.x",)),
        MigrationDef(version=1, name="a", schema_up=("CREATE INDEX i IF NOT EXISTS FOR (n:X) ON (n.y)",)),
        MigrationDef(version=1, name="renamed", up=("MATCH (n) SET n.x = 1",)),
    ]:
        assert variant.checksum != base.checksum


def test_reversibility():
    assert MigrationDef(version=1, name="noop").reversible
    assert MigrationDef(version=1, name="ok", up=("U",), down=("D",)).reversible
    assert MigrationDef(version=1, name="schema", schema_up=("S",), schema_down=("T",)).reversible
    assert not MigrationDef(version=1, name="oneway", up=("U",)).reversible


def test_shipped_migrations_load_and_m0003_is_reversible():
    """The real migrations/ package: versions contiguous from 1, and m0003
    (org-scoped LLM providers) present and reversible. No max-version pin —
    later migrations may land without touching this test."""
    from migrations import migration_modules

    defs = load_definitions(migration_modules())
    versions = [d.version for d in defs]
    assert versions == list(range(1, len(defs) + 1))  # contiguous from 1

    by_version = {d.version: d for d in defs}
    m3 = by_version.get(3)
    assert m3 is not None and m3.name == "org-scoped-llm-providers"
    assert m3.reversible
    assert any("SET p.org_uid = 'local-org'" in stmt for stmt in m3.up)
    assert any("migrated_from_shared" in stmt for stmt in m3.down)


def test_plan_applies_pending_in_order():
    code = [MigrationDef(version=v, name=f"m{v}") for v in (1, 2, 3)]
    plan = build_plan(code, [_applied(code[0])])
    assert [m.version for m in plan.to_apply] == [2, 3]
    assert plan.to_revert == []
    assert not plan.noop


def test_plan_noop_when_in_sync():
    code = [MigrationDef(version=1, name="m1")]
    plan = build_plan(code, [_applied(code[0])])
    assert plan.noop


def test_plan_reverts_versions_ahead_of_code_newest_first():
    # The Coolify rollback case: old image (2 migrations) boots against a DB
    # where the newer image applied 3 and 4.
    code = [MigrationDef(version=1, name="m1"), MigrationDef(version=2, name="m2")]
    newer = [
        MigrationDef(version=3, name="m3", up=("U3",), down=("D3",)),
        MigrationDef(version=4, name="m4", up=("U4",), down=("D4",)),
    ]
    applied = [_applied(m) for m in code + newer]
    plan = build_plan(code, applied)
    assert [r.version for r in plan.to_revert] == [4, 3]
    assert plan.to_apply == []


def test_plan_rejects_edited_applied_migration():
    code = [MigrationDef(version=1, name="m1", up=("EDITED",))]
    applied = [AppliedRecord(version=1, name="m1", checksum="original-checksum")]
    with pytest.raises(MigrationError, match="immutable"):
        build_plan(code, applied)


def test_plan_rejects_diverged_history():
    # DB has version 2 but code's set below its own max doesn't include it.
    code = [MigrationDef(version=1, name="m1"), MigrationDef(version=3, name="m3")]
    applied = [AppliedRecord(version=2, name="ghost", checksum="x")]
    with pytest.raises(MigrationError, match="diverged"):
        # Note: load_definitions would already reject this code set; build_plan
        # guards independently for repaired/hand-edited ledgers.
        build_plan(code, applied)
