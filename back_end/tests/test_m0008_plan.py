"""m0008 (agents-scheduled-agents) migration plan — pure statement pins.

The migration itself runs against Neo4j; here we pin the plan's shape and
the orderings correctness depends on: the AgentPrompt→Agent label swap must
precede the overlay-revision rewrites that match `(a:Agent …)`, and every
Investigation data-carry statement must precede the `DETACH DELETE` that
removes the Investigation nodes.
"""

import migrations.m0008_agents_scheduled_agents as m8
from infrastructure.migration_runner import load_definitions
from migrations import migration_modules


def test_version_and_statement_shape():
    assert m8.VERSION == 8
    for block in (m8.SCHEMA_UP, m8.SCHEMA_DOWN, m8.UP, m8.DOWN):
        assert block, "empty migration block"
        for stmt in block:
            assert isinstance(stmt, str) and stmt.strip()


def test_registered_and_reversible():
    defs = load_definitions(migration_modules())
    m = next(d for d in defs if d.version == 8)
    assert m.name == "agents-scheduled-agents"
    assert m.reversible


def test_investigation_data_is_carried_before_the_delete():
    delete_idx = next(i for i, s in enumerate(m8.UP) if "DETACH DELETE i" in s)
    for i, stmt in enumerate(m8.UP):
        if ":Investigation" in stmt:
            assert i <= delete_idx, (
                f"UP[{i}] touches :Investigation after the DETACH DELETE"
            )


def test_label_swap_precedes_the_agent_rewrites():
    swap_idx = next(i for i, s in enumerate(m8.UP) if "REMOVE p:AgentPrompt" in s)
    agent_idxs = [
        i for i, s in enumerate(m8.UP) if "(a:Agent {provenance: 'system'})" in s
    ]
    assert agent_idxs, "no overlay-revision rewrite statements found"
    assert swap_idx < min(agent_idxs)
