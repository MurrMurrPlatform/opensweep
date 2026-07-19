"""In-flight run guards — pure filter logic + the 409 detail contract (V3:
runs carry their entity links directly; no Investigation join)."""

from types import SimpleNamespace

from domains.runs.services.active_runs import (
    ACTIVE_RUN_STATUSES,
    WRITE_PLAYBOOKS,
    blocking_run,
    conflict_detail,
    filter_active_runs,
)


def _run(
    uid="r1",
    status="running",
    repository_uid="repo1",
    linked_pr_uid="",
    linked_ticket_uid="",
    linked_finding_uid="",
    playbook="ask",
    scheduled_agent_uid="",
):
    return SimpleNamespace(
        uid=uid,
        status=status,
        repository_uid=repository_uid,
        linked_pr_uid=linked_pr_uid,
        linked_ticket_uid=linked_ticket_uid,
        linked_finding_uid=linked_finding_uid,
        playbook=playbook,
        scheduled_agent_uid=scheduled_agent_uid,
    )


def test_active_statuses_are_queued_running_paused_quota():
    # awaiting_input deliberately NOT active: the turn is over; a follow-up
    # is a new turn (V3 §2).
    assert ACTIVE_RUN_STATUSES == {"queued", "running", "paused_quota"}


def test_terminal_and_awaiting_runs_never_match():
    for status in ("awaiting_input", "ended", "failed", "cancelled", "limit_exceeded"):
        runs = [_run(status=status, linked_pr_uid="pr1")]
        assert filter_active_runs(runs, pull_request_uid="pr1") == []


def test_all_active_statuses_match():
    for status in ("queued", "running", "paused_quota"):
        runs = [_run(status=status, linked_pr_uid="pr1")]
        assert len(filter_active_runs(runs, pull_request_uid="pr1")) == 1


def test_linked_uid_must_match():
    runs = [
        _run(uid="r1", linked_pr_uid="pr1"),
        _run(uid="r2", linked_pr_uid="pr2"),
        _run(uid="r3", linked_ticket_uid="t1"),
    ]
    assert [r.uid for r in filter_active_runs(runs, pull_request_uid="pr1")] == ["r1"]
    assert [r.uid for r in filter_active_runs(runs, ticket_uid="t1")] == ["r3"]


def test_playbook_filter():
    runs = [
        _run(uid="r1", playbook="review"),
        _run(uid="r2", playbook="ask"),
    ]
    assert [r.uid for r in filter_active_runs(runs, playbooks=["review"])] == ["r1"]


def test_repository_filter():
    runs = [
        _run(uid="r1", repository_uid="repo1"),
        _run(uid="r2", repository_uid="repo2"),
    ]
    assert [r.uid for r in filter_active_runs(runs, repository_uid="repo1")] == ["r1"]


def test_combined_link_and_playbook():
    runs = [
        _run(uid="r1", linked_pr_uid="pr1", playbook="fix"),
        _run(uid="r2", linked_pr_uid="pr1", playbook="review"),
    ]
    got = filter_active_runs(runs, pull_request_uid="pr1", playbooks=["review"])
    assert [r.uid for r in got] == ["r2"]


def test_finding_uid_filter():
    runs = [
        _run(uid="r1", linked_finding_uid="f1", playbook="chat"),
        _run(uid="r2", linked_finding_uid="f2", playbook="chat"),
    ]
    assert [r.uid for r in filter_active_runs(runs, finding_uid="f1")] == ["r1"]


def test_write_playbooks_are_implement_fix_and_thread():
    # `thread` commits into a work branch too (rev2) — same one-writer-per-
    # target serialization applies.
    assert WRITE_PLAYBOOKS == {"implement", "fix", "thread"}


def test_chat_never_blocks_and_is_never_blocked():
    chat = _run(uid="c1", playbook="chat")
    # A chat run in flight blocks nothing.
    for playbook in ("review", "fix", "implement", "verify"):
        assert blocking_run([chat], playbook=playbook) is None
    # Dispatching chat is never blocked, even by a write run.
    assert blocking_run([_run(playbook="fix"), _run(playbook="review")], playbook="chat") is None


def test_same_playbook_duplicate_blocks():
    for playbook in ("review", "verify", "fix", "implement"):
        active = _run(uid="a1", playbook=playbook)
        assert blocking_run([active], playbook=playbook) is active


def test_write_vs_write_blocks_across_playbooks():
    fix = _run(uid="w1", playbook="fix")
    assert blocking_run([fix], playbook="implement") is fix
    implement = _run(uid="w2", playbook="implement")
    assert blocking_run([implement], playbook="fix") is implement


def test_read_runs_overlap_writes_and_each_other():
    # Review dispatch while a fix run writes: allowed (read+write overlap).
    assert blocking_run([_run(playbook="fix")], playbook="review") is None
    # Verify while a review reads: allowed.
    assert blocking_run([_run(playbook="review")], playbook="verify") is None
    # Fix while a review reads: allowed — only write-vs-write races.
    assert blocking_run([_run(playbook="review")], playbook="fix") is None


def test_conflict_detail_shape_lets_the_ui_link_the_run():
    run = _run(uid="r1", scheduled_agent_uid="i1")
    detail = conflict_detail("a review run is already in progress for this PR", run)
    assert detail == {
        "message": "a review run is already in progress for this PR",
        "run_uid": "r1",
        "scheduled_agent_uid": "i1",
    }
    assert all(isinstance(v, str) for v in detail.values())


def test_active_runs_route_is_mounted_before_the_uid_route():
    """/active must not be swallowed by /{uid}."""
    from app import app

    paths = list(app.openapi().get("paths", {}).keys())
    active = "/api/v1/runs/active"
    uid = "/api/v1/runs/{uid}"
    assert active in paths and uid in paths
    assert paths.index(active) < paths.index(uid)

    ops = {
        op.get("operationId")
        for methods in app.openapi()["paths"].values()
        for op in methods.values()
        if isinstance(op, dict)
    }
    assert "opensweep_list_active_runs" in ops
