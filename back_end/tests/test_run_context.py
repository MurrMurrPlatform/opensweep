"""Run conversation briefing — the agent must receive the entity UIDs, not
just titles: every opensweep_platform_* tool takes explicit uids, so a briefing
without them leaves the agent unable to touch the ledger it is discussing."""

from types import SimpleNamespace

from domains.investigations.services.run_context import render_run_context


def test_empty_briefing_still_renders_the_chat_framing():
    text = render_run_context()
    assert "chatting with a maintainer" in text
    assert "Identifiers" not in text


def test_identifiers_block_carries_all_linked_uids():
    repo = SimpleNamespace(uid="repo-uid", github_owner="o", github_repo="r", default_branch="main")
    pr = SimpleNamespace(uid="pr-uid", github_number=7, title="t", head_ref="h", base_ref="b",
                         state="open", head_sha="abc", converged=False, convergence={})
    ticket = SimpleNamespace(uid="ticket-uid", title="T", status="todo", priority="high",
                             description="d", acceptance_criteria=["a"])
    finding = SimpleNamespace(uid="finding-uid", title="F", severity="high", tags=[],
                              status="open", why_it_matters="w", suggested_fix="s",
                              affected_paths=[])
    text = render_run_context(
        run_uid="run-uid", repo=repo, pr=pr, ticket=ticket, finding=finding
    )
    assert "run_uid: run-uid" in text
    assert "repository_uid: repo-uid" in text
    assert "pull_request_uid: pr-uid" in text
    assert "ticket_uid: ticket-uid" in text
    assert "finding_uid: finding-uid" in text
    assert "opensweep_platform_*" in text


def test_resolution_lines_carry_finding_uids():
    pr = SimpleNamespace(uid="pr-uid", github_number=7, title="t", head_ref="h", base_ref="b",
                         state="open", head_sha="abc", converged=False, convergence={})
    resolution = SimpleNamespace(state="open", blocking=True, finding_title="Bug",
                                 finding_uid="f-123", finding_severity="high", finding_tags=[])
    text = render_run_context(repo=None, pr=pr, resolutions=[resolution])
    assert "finding_uid f-123" in text


def test_oversized_section_is_capped_without_starving_the_rest():
    ticket = SimpleNamespace(uid="ticket-uid", title="T", status="todo", priority="high",
                             description="x" * 10_000, acceptance_criteria=[])
    finding = SimpleNamespace(uid="finding-uid", title="F", severity="high", tags=[],
                              status="open", why_it_matters="w", suggested_fix="s",
                              affected_paths=[])
    text = render_run_context(run_uid="run-uid", ticket=ticket, finding=finding)
    # The finding section (after the huge ticket) must survive.
    assert 'FINDING "F"' in text
    assert "finding_uid: finding-uid" in text
