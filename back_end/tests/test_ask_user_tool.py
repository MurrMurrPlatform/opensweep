"""ask_user tool: registration + validation surface (pure), plus the
attention side-effects (audit event + needs_input flag) with faked storage."""

from importlib import import_module
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.platform_tools.ask_user import _validate
from domains.platform_tools.dispatcher import _TOOLS

# The package __init__ rebinds `ask_user` to the function — import the module
# itself for monkeypatching.
au = import_module("domains.platform_tools.ask_user")


def test_tool_is_registered_in_dispatcher():
    assert "ask_user" in _TOOLS


def test_validation_rejects_empty_question():
    with pytest.raises(HTTPException) as exc:
        _validate(thread_uid="th-1", question="  ", options=[])
    assert exc.value.status_code == 422


def test_validation_rejects_missing_thread():
    with pytest.raises(HTTPException):
        _validate(thread_uid="", question="Which auth flow?", options=[])


def test_validation_caps_options():
    with pytest.raises(HTTPException):
        _validate(thread_uid="th-1", question="q", options=[str(i) for i in range(7)])
    _validate(thread_uid="th-1", question="q", options=["a", "b"])  # ok


# ── attention side-effects (faked storage) ───────────────────────────────────


class _Saveable(SimpleNamespace):
    async def save(self):
        return self


@pytest.fixture
def wired(monkeypatch):
    """Fake thread resolution, run lookup, audit, and the comment mirror."""
    thread = _Saveable(
        uid="th-1",
        phase="build",
        events=[],
        subject_ticket_uid="tk-1",
        repository_uid="repo-1",
        updated_at=None,
    )
    run = _Saveable(uid="run-1", usage={})
    audits: list[dict] = []

    from domains.threads.services import thread_service

    async def _resolve(candidate, *, run_uid=""):
        return thread

    monkeypatch.setattr(thread_service, "resolve_thread", _resolve)

    from domains.investigations import models as inv_models

    class _Nodes:
        async def get_or_none(self, *, uid):
            return run if uid == run.uid else None

    monkeypatch.setattr(inv_models.Run, "nodes", _Nodes())

    async def _capture_audit(**kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(au, "write_audit", _capture_audit)

    from domains.comments import service as comment_service

    async def _mirror(**kwargs):
        return SimpleNamespace(uid="c-1")

    monkeypatch.setattr(comment_service, "create_comment", _mirror)
    return thread, run, audits


async def test_question_writes_an_attention_audit_event(wired):
    thread, _, audits = wired
    await au.ask_user(
        thread_uid="th-1", question="Merge now or wait?", executor="run-1"
    )
    (audit,) = audits
    assert audit["kind"] == "thread.question_asked"
    assert audit["subject_uid"] == thread.uid
    assert audit["subject_type"] == "Thread"
    # Passed explicitly: Thread nodes carry repository_uid, but the audit
    # helper's derive step needs a live DB — the tool must not depend on it.
    assert audit["repository_uid"] == "repo-1"
    assert audit["payload"]["title"] == "Merge now or wait?"


async def test_question_flags_the_calling_run_needs_input(wired):
    _, run, _ = wired
    await au.ask_user(thread_uid="th-1", question="Which auth flow?", executor="run-1")
    assert run.usage["needs_input"] is True


async def test_manual_executor_does_not_touch_runs(wired):
    _, run, audits = wired
    await au.ask_user(thread_uid="th-1", question="q?", executor="manual")
    assert run.usage == {}
    assert len(audits) == 1  # the audit event still fires
