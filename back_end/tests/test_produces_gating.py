"""Produces gating — the write path (`code-changes`) is fenced off from
user creation, scheduling, and direct dispatch; system-reserved produces
stay system-only. Pure: no DB (the dispatch guards fire before any query)."""

import pytest
from fastapi import HTTPException

from domains.agents.services.agent_service import validate_produces
from domains.agents.services.dispatch import dispatch_agent
from domains.agents.services.scheduled_agent_service import _reject_write_agent
from domains.runs.services.lifecycle import LifecycleError


class _StubAgent:
    def __init__(self, *, produces="findings", enabled=True):
        self.uid = "agent-1"
        self.title = "Stub agent"
        self.prompt = ""
        self.produces = produces
        self.enabled = enabled
        self.provenance = "user"
        self.source_url = ""
        self.default_effort = "normal"


# ── validate_produces ────────────────────────────────────────────────────────


def test_user_creatable_produces_are_accepted():
    assert validate_produces("findings") == "findings"
    assert validate_produces("answer") == "answer"
    assert validate_produces("documentation") == "documentation"


def test_system_reserved_produces_are_422():
    for produces in ("analysis", "review-verdict"):
        with pytest.raises(HTTPException) as exc:
            validate_produces(produces)
        assert exc.value.status_code == 422
        assert "system" in exc.value.detail.lower()


def test_code_changes_requires_the_write_gate():
    with pytest.raises(HTTPException) as exc:
        validate_produces("code-changes")
    assert exc.value.status_code == 422
    assert validate_produces("code-changes", allow_write=True) == "code-changes"


def test_unknown_produces_is_422():
    with pytest.raises(HTTPException) as exc:
        validate_produces("nonsense")
    assert exc.value.status_code == 422


# ── scheduling never accepts write agents ────────────────────────────────────


def test_scheduling_a_write_agent_is_422():
    with pytest.raises(HTTPException) as exc:
        _reject_write_agent(_StubAgent(produces="code-changes"))
    assert exc.value.status_code == 422


def test_scheduling_a_read_agent_passes_the_gate():
    _reject_write_agent(_StubAgent(produces="findings"))  # no raise


# ── dispatch guards fire before any DB work ──────────────────────────────────


async def test_dispatch_refuses_write_agents_outright():
    with pytest.raises(LifecycleError):
        await dispatch_agent(
            agent=_StubAgent(produces="code-changes"),
            repository_uid="repo-1",
        )


async def test_dispatch_refuses_disabled_agents():
    with pytest.raises(LifecycleError) as exc:
        await dispatch_agent(
            agent=_StubAgent(produces="findings", enabled=False),
            repository_uid="repo-1",
        )
    assert "disabled" in str(exc.value)
