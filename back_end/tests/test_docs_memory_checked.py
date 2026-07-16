"""Pure-Python tests for the KNOWLEDGE_V3 primitives.

DB-bound flows (CRUD, accept/reject, stamping) are integration-tested;
here we pin the pure logic: slug normalization, memory fingerprint dedup
inputs, staleness comparison, and checked outcome mapping.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from domains.checked.services.checked_service import _outcome_for_run
from domains.docs.services.doc_service import normalize_slug
from domains.memory.services.memory_service import _fingerprint, _possibly_stale


def test_normalize_slug_kebab_cases_and_caps_length():
    assert normalize_slug("Feature: Login with Email!") == "feature-login-with-email"
    assert normalize_slug("  Conventions  ") == "conventions"
    assert normalize_slug("") == ""
    assert len(normalize_slug("x" * 300)) <= 120


def test_normalize_slug_preserves_folders():
    assert normalize_slug("Backend/Queue Workers") == "backend/queue-workers"
    assert normalize_slug("backend//queue-workers/") == "backend/queue-workers"
    assert normalize_slug("/deployment/Terraform!") == "deployment/terraform"


def test_fingerprint_ignores_case_and_whitespace_of_title():
    a = _fingerprint("Flaky Redis fixture", "body text")
    b = _fingerprint("  flaky redis fixture ", "body text")
    assert a == b
    assert a != _fingerprint("flaky redis fixture", "different body")


def test_possibly_stale_compares_anchor_change_to_update():
    now = datetime.now(UTC)
    fresh = SimpleNamespace(anchor_uid="n1", updated_at=now)
    stale = SimpleNamespace(anchor_uid="n1", updated_at=now - timedelta(days=2))
    unanchored = SimpleNamespace(anchor_uid="", updated_at=now - timedelta(days=2))
    change_times = {"n1": now - timedelta(days=1)}
    assert _possibly_stale(fresh, change_times) is False
    assert _possibly_stale(stale, change_times) is True
    assert _possibly_stale(unanchored, change_times) is False
    assert _possibly_stale(stale, {}) is False


def test_checked_outcome_collapses_failures():
    assert _outcome_for_run(status="completed", findings_count=0) == "clean"
    assert _outcome_for_run(status="completed", findings_count=3) == "findings"
    for status in ("failed", "cancelled", "limit_exceeded", "queued", ""):
        assert _outcome_for_run(status=status, findings_count=1) == "failed"


def test_checked_outcome_awaiting_input_counts_as_success():
    # V3 runs land in awaiting_input after a successful turn; the stamp is
    # written by the per-turn hook, so treat it like completion.
    assert _outcome_for_run(status="awaiting_input", findings_count=0) == "clean"
    assert _outcome_for_run(status="awaiting_input", findings_count=2) == "findings"
