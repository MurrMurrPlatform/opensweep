"""Deletion of campaign and run records — DB seams monkeypatched.

Campaigns: live states (running/finalizing) 409 — cancel first; settled
states delete the node and write the audit trail. Runs: active or
awaiting-input runs 409 (they hold a live turn or workspace); settled runs
delete the node plus their on-disk event stream.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.campaigns.models import Campaign
from domains.campaigns.services import campaign_service


def _campaign(**overrides):
    fields = {
        "uid": "c1",
        "repository_uid": "repo1",
        "title": "t",
        "status": "planning",
        "template": "full",
        "lens_keys": ["bugs"],
        "k": 3,
        "parts": [],
        "max_parallel": 2,
    }
    fields.update(overrides)
    return Campaign(**fields)


@pytest.fixture
def campaign_seams(monkeypatch):
    state = SimpleNamespace(campaign=None, deleted=0, audits=[])

    async def fake_get(uid):
        return state.campaign

    async def fake_delete(self):
        state.deleted += 1

    async def fake_audit(**kwargs):
        state.audits.append(kwargs)

    monkeypatch.setattr(campaign_service, "get", fake_get)
    monkeypatch.setattr(Campaign, "delete", fake_delete)
    monkeypatch.setattr(campaign_service, "write_audit", fake_audit)
    return state


@pytest.mark.parametrize("status", ["running", "finalizing"])
async def test_delete_live_campaign_409s(campaign_seams, status):
    campaign_seams.campaign = _campaign(status=status)
    with pytest.raises(HTTPException) as exc:
        await campaign_service.delete("c1", actor_uid="u1")
    assert exc.value.status_code == 409
    assert "cancel it before deleting" in str(exc.value.detail)
    assert campaign_seams.deleted == 0


@pytest.mark.parametrize("status", ["planning", "done", "failed", "cancelled"])
async def test_delete_settled_campaign_removes_node_and_audits(
    campaign_seams, status
):
    campaign_seams.campaign = _campaign(status=status)
    await campaign_service.delete("c1", actor_uid="u1")
    assert campaign_seams.deleted == 1
    (audit,) = campaign_seams.audits
    assert audit["kind"] == "campaign.deleted"
    assert audit["subject_uid"] == "c1"
    assert audit["repository_uid"] == "repo1"
    assert audit["actor_uid"] == "u1"
    assert audit["payload"]["status"] == status


# ── run deletion (endpoint-level; the route owns the guard) ─────────────────


def _user():
    from domains.users.schemas import UserDTO

    return UserDTO(
        uid="u1",
        email="u@example.test",
        display_name="U",
        role="admin",
        org_uid="org-a",
        org_role="owner",
        is_platform_admin=False,
    )


@pytest.fixture
def run_seams(monkeypatch, tmp_path):
    import api.v1.runs as runs_api
    import domains.runs.services.run_events as run_events
    import infrastructure.audit as audit_mod

    state = SimpleNamespace(run=None, deleted=0, audits=[], events_file=None)

    async def fake_get_or_none(uid=None):
        return state.run

    async def fake_allow(repository_uid, org_uid):
        return None

    async def fake_audit(**kwargs):
        state.audits.append(kwargs)

    events_file = tmp_path / "run1.events.jsonl"
    events_file.write_text('{"type":"narration"}\n')
    state.events_file = events_file

    monkeypatch.setattr(
        runs_api, "Run", SimpleNamespace(nodes=SimpleNamespace(get_or_none=fake_get_or_none))
    )
    monkeypatch.setattr(runs_api, "require_repo_in_org", fake_allow)
    monkeypatch.setattr(audit_mod, "write_audit", fake_audit)
    monkeypatch.setattr(run_events, "events_path", lambda uid: events_file)
    return state


def _run(state, **overrides):
    async def delete(self=None):
        state.deleted += 1

    fields = dict(
        uid="run1", repository_uid="repo1", status="ended", delete=delete
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


@pytest.mark.parametrize(
    "status", ["queued", "running", "paused_quota", "awaiting_input"]
)
async def test_delete_active_run_409s(run_seams, status):
    from api.v1.runs import delete_run

    run_seams.run = _run(run_seams, status=status)
    with pytest.raises(HTTPException) as exc:
        await delete_run("run1", user=_user())
    assert exc.value.status_code == 409
    assert run_seams.deleted == 0
    assert run_seams.events_file.exists()  # transcript untouched


@pytest.mark.parametrize(
    "status", ["ended", "failed", "cancelled", "limit_exceeded"]
)
async def test_delete_settled_run_removes_node_events_and_audits(
    run_seams, status
):
    from api.v1.runs import delete_run

    run_seams.run = _run(run_seams, status=status)
    await delete_run("run1", user=_user())
    assert run_seams.deleted == 1
    assert not run_seams.events_file.exists()
    (audit,) = run_seams.audits
    assert audit["kind"] == "run.deleted"
    assert audit["subject_uid"] == "run1"
    assert audit["repository_uid"] == "repo1"
    assert audit["payload"]["status"] == status


async def test_delete_missing_run_404s(run_seams):
    from api.v1.runs import delete_run

    run_seams.run = None
    with pytest.raises(HTTPException) as exc:
        await delete_run("nope", user=_user())
    assert exc.value.status_code == 404
