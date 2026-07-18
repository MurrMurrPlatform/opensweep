"""Derived progress: pure computation from platform-observed thread facts."""

from domains.threads.services.progress import compute_progress


def _q(status):
    return {"type": "question", "status": status}


def test_refining_counts_questions_and_plan():
    p = compute_progress(
        phase="refining",
        plan_state="drafted",
        events=[_q("answered"), _q("answered"), _q("open")],
    )
    assert p["questions_answered"] == 2 and p["questions_open"] == 1
    assert "2/3 questions answered" in p["label"]
    assert "plan drafted" in p["label"]


def test_refining_without_activity_reads_exploring():
    p = compute_progress(phase="refining", plan_state="none", events=[])
    assert p["label"] == "Planning — exploring"


def test_implementing_reflects_pr_and_gate():
    p = compute_progress(
        phase="implementing",
        plan_state="approved",
        events=[{"type": "pr_opened"}],
    )
    assert p["pr_opened"] is True
    assert "plan approved" in p["label"] and "PR open" in p["label"]


def test_in_review_shows_verdict_and_rounds():
    events = [
        {"type": "review_verdict", "result": "request_changes"},
        {"type": "fix_started"},
        {"type": "review_verdict", "result": "approve"},
    ]
    p = compute_progress(phase="in_review", plan_state="approved", events=events)
    assert p["last_verdict"] == "approve"
    assert p["fix_rounds"] == 1
    assert "last verdict: approve" in p["label"] and "fix round 1" in p["label"]


def test_done_label():
    p = compute_progress(phase="done", plan_state="approved", events=[])
    assert p["label"] == "Done — merged"
