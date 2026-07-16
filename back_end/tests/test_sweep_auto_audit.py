"""Auto-audit surface (§F) — signatures, job type, scanner predicate.

run_auto_audit itself touches Neo4j + dispatch; its selection math is
covered purely in test_audit_selection.py.
"""

import inspect

from domains.investigations.services.job_types import get_job_type
from domains.investigations.services.schedule_scanner import should_auto_audit
from domains.investigations.services.sweep import AuditResult, run_auto_audit


def test_audit_stale_job_type_exists():
    jt = get_job_type("audit-stale")
    assert jt is not None
    assert "stale" in jt.description.lower()


def test_run_auto_audit_signature():
    params = inspect.signature(run_auto_audit).parameters
    assert {"repository_uid", "limit", "triggered_by", "agent_prompt_uid", "custom_intent"} <= set(params)
    assert params["limit"].default == 3


def test_audit_result_carries_selection_provenance():
    result = AuditResult(repository_uid="r1", doc_count=0)
    assert result.selected == []


def test_scanner_predicate_gates_on_job_type_and_dial():
    assert should_auto_audit("audit-stale", "ask-before-run")
    assert should_auto_audit("audit-stale", "auto-run-any")
    # disabled is the kill-safety even with a cron set.
    assert not should_auto_audit("audit-stale", "disabled")
    # Other job types keep the classic single-run dispatch path.
    assert not should_auto_audit("audit", "auto-run-any")


def test_seeded_investigation_is_inert_until_a_cron_is_set():
    from domains.investigations.services.seeding import (
        AUDIT_STALE_TITLE,
        seed_audit_stale_investigation,
    )

    assert AUDIT_STALE_TITLE == "Audit stale code"
    # Contract documented in the seeder: schedule="" (cron is the opt-in).
    src = inspect.getsource(seed_audit_stale_investigation)
    assert 'schedule=""' in src
