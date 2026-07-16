"""opensweep/review commit-status mapping (§C) — pure table."""

from domains.delivery.services.pull_request_service import review_status_for


def test_dispatch_publishes_pending_with_depth():
    state, desc = review_status_for("", 0, depth="quick")
    assert state == "pending"
    assert "depth=quick" in desc


def test_approve_is_success():
    state, desc = review_status_for("approve", 0)
    assert state == "success"
    assert "0 new blocking" in desc


def test_needs_human_is_error():
    state, desc = review_status_for("needs_human", 0)
    assert state == "error"
    assert "human" in desc


def test_request_changes_pending_while_verification_runs():
    state, desc = review_status_for("request_changes", 3, "pending")
    assert state == "pending"
    assert "verification in progress" in desc


def test_request_changes_final_is_failure_with_titles():
    state, desc = review_status_for(
        "request_changes", 2, "", finding_titles=["Race in cache", "Missing authz"]
    )
    assert state == "failure"
    assert "2 blocking" in desc
    assert "Race in cache" in desc


def test_failed_verification_reads_as_final_failure():
    # fail closed: findings stay confirmed, status shows the block.
    state, _ = review_status_for("request_changes", 2, "failed")
    assert state == "failure"
