"""Pure tests for the two-stage sweep service.

`run_generate_docs` and `run_audit` touch Neo4j (Doc, ScheduledAgent,
audit log) and the LLM dispatch path, so we exercise them indirectly:
we assert the public surface, the produces mapping, and the estimate.
Neo4j-bound behavior lives in integration tests, not here.
"""

import inspect

from domains.agents.services.registry import PRODUCES_TO_PLAYBOOK
from domains.agents.services.seed_agent_bases import _AGENT_BASES
from domains.runs.services.sweep import estimate_sweep_cost, run_audit


def test_generate_docs_agent_produces_the_doc_tree():
    assert _AGENT_BASES["generate-docs"]["produces"] == "doc-tree"
    assert PRODUCES_TO_PLAYBOOK["doc-tree"] == "ask"


def test_run_audit_has_no_concern_taxonomy_parameter():
    params = inspect.signature(run_audit).parameters
    assert "concerns" not in params
    assert "custom_intent" in params


def test_estimate_reports_two_stage_shape():
    estimate = estimate_sweep_cost(7)
    assert estimate["docs"] == 7
    assert estimate["generate_docs_runs"] == 1
    assert estimate["audit_runs_if_all_selected"] == 7
    assert "note" in estimate
