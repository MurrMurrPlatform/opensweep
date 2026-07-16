"""Regression: POST /api/v1/runs must reject a repository outside the
caller's org for BOTH playbooks (the ask path previously skipped the check).

DB-free — the tenancy dependency is faked; the test pins that create_run
calls require_repo_in_org before any playbook logic runs."""

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


async def test_create_run_guards_repo_org_before_dispatch(monkeypatch):
    import api.v1.runs as runs

    calls: list[tuple[str, str]] = []

    async def fake_require(repo, org):
        calls.append((repo, org))
        raise HTTPException(status_code=404, detail="not found")

    async def boom_trigger(*a, **k):  # must never run for a cross-org repo
        raise AssertionError("trigger_run reached despite cross-org repository")

    async def boom_chat(*a, **k):
        raise AssertionError("_create_chat_run reached despite cross-org repository")

    monkeypatch.setattr(runs, "require_repo_in_org", fake_require)
    monkeypatch.setattr(runs, "trigger_run", boom_trigger)
    monkeypatch.setattr(runs, "_create_chat_run", boom_chat)

    from domains.investigations.schemas import CreateRunRequest, Playbook
    from domains.users.schemas import UserDTO

    user = UserDTO(uid="u", email="e@x.y", display_name="U", role="maintainer", org_uid="org-a")

    for pb in (Playbook.ASK, Playbook.CHAT):
        with pytest.raises(HTTPException) as exc:
            await runs.create_run(
                CreateRunRequest(repository_uid="repo-in-org-b", playbook=pb), user=user
            )
        assert exc.value.status_code == 404

    # guard hit first for both playbooks, always with the caller's org
    assert calls == [("repo-in-org-b", "org-a"), ("repo-in-org-b", "org-a")]
