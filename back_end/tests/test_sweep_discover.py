"""Pure tests for the two-stage sweep service.

`run_generate_docs` and `run_audit` touch Neo4j (Doc, Investigation,
audit log) and the LLM dispatch path, so we exercise them indirectly:
we assert the public surface, the job-type shape, and the estimate.
Neo4j-bound behavior lives in integration tests, not here.
"""

import inspect

from domains.runs.services.job_types import get_job_type
from domains.runs.services.sweep import estimate_sweep_cost, run_audit


def test_generate_docs_job_type_exists():
    jt = get_job_type("generate-docs")
    assert jt is not None
    assert "propose_doc_edit" in jt.intent


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
