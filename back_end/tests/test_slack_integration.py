"""Slack integration — signing, event mapping, formatting, inbound parsing,
and the audit-hook prefilter. DB-free (fakes/monkeypatching), matching the
test style of test_github_app.py / test_run_surface.py."""

import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import pytest

from domains.slack import inbound
from domains.slack.events import (
    CATALOG,
    EVENT_TYPES,
    RELEVANT_AUDIT_KINDS,
    event_types_for,
)
from domains.slack.formatting import format_event_message, subject_link, to_mrkdwn
from domains.slack.notify import notify_slack_of_event
from domains.slack.signing import (
    mint_install_state,
    verify_install_state,
    verify_slack_signature,
)

pytestmark = pytest.mark.asyncio

SECRET = "8f742231b10e8888abcd99yyyzzz85a5"


def _sign(secret: str, ts: int, body: bytes) -> str:
    base = b"v0:" + str(ts).encode() + b":" + body
    return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


# ── request signature ────────────────────────────────────────────────────────


def test_signature_roundtrip():
    ts = int(time.time())
    body = b'{"type":"url_verification"}'
    sig = _sign(SECRET, ts, body)
    assert verify_slack_signature(
        signing_secret=SECRET, timestamp=str(ts), signature=sig, body=body
    )


def test_signature_rejects_wrong_secret_and_tamper():
    ts = int(time.time())
    body = b"payload"
    sig = _sign(SECRET, ts, body)
    assert not verify_slack_signature(
        signing_secret="other-secret", timestamp=str(ts), signature=sig, body=body
    )
    assert not verify_slack_signature(
        signing_secret=SECRET, timestamp=str(ts), signature=sig, body=b"payload2"
    )


def test_signature_rejects_replay_window():
    ts = int(time.time()) - 600  # beyond the 5-minute window
    body = b"payload"
    sig = _sign(SECRET, ts, body)
    assert not verify_slack_signature(
        signing_secret=SECRET, timestamp=str(ts), signature=sig, body=body
    )


def test_signature_rejects_missing_pieces():
    assert not verify_slack_signature(
        signing_secret="", timestamp="1", signature="v0=x", body=b""
    )
    assert not verify_slack_signature(
        signing_secret=SECRET, timestamp=None, signature="v0=x", body=b""
    )
    assert not verify_slack_signature(
        signing_secret=SECRET, timestamp="not-a-number", signature="v0=x", body=b""
    )


# ── install state ────────────────────────────────────────────────────────────


def test_install_state_roundtrip():
    state = mint_install_state("org-abc123", "user-42")
    assert state.startswith("sls_")
    assert verify_install_state(state) == ("org-abc123", "user-42")
    assert verify_install_state(mint_install_state("org-abc123")) == ("org-abc123", "")


def test_install_state_rejects_tamper_and_expiry():
    now = int(time.time())
    state = mint_install_state("org-abc123", "user-42", now=now)
    assert verify_install_state(state[:-1] + ("0" if state[-1] != "0" else "1")) == ("", "")
    assert verify_install_state(state, now=now + 3599) == ("org-abc123", "user-42")
    assert verify_install_state(state, now=now + 3601) == ("", "")
    assert verify_install_state("kis_1.2.3.4.5") == ("", "")
    assert verify_install_state("") == ("", "")


def test_install_state_uid_swap_breaks_signature():
    state = mint_install_state("org-a", "user-1")
    parts = state[len("sls_"):].split(".")
    assert verify_install_state(f"sls_{parts[0]}.org-b.{parts[2]}.{parts[3]}.{parts[4]}") == ("", "")
    assert verify_install_state(f"sls_{parts[0]}.{parts[1]}.user-2.{parts[3]}.{parts[4]}") == ("", "")


# ── event catalog + mapping ──────────────────────────────────────────────────


def test_catalog_types_are_unique_and_mapped():
    assert len({e.event_type for e in CATALOG}) == len(CATALOG)
    # Every audit kind maps only onto catalogued event types.
    for kind in RELEVANT_AUDIT_KINDS:
        for event_type in event_types_for(kind, {}):
            assert event_type in EVENT_TYPES, (kind, event_type)
    # Every catalogued type is reachable from at least one audit kind.
    reachable = {
        t for kind in RELEVANT_AUDIT_KINDS for t in event_types_for(kind, {"result": "needs_human"})
    }
    assert reachable == EVENT_TYPES


def test_event_mapping_specifics():
    assert event_types_for("run.ended", {}) == ["run.completed"]
    assert event_types_for("ticket.done_via_merge", {}) == ["ticket.status_changed"]
    assert event_types_for("run.paused_quota", {}) == ["attention.required"]
    assert event_types_for("not.an.event", {}) == []


def test_needs_human_verdict_also_raises_attention():
    assert event_types_for("verdict.submitted", {"result": "approve"}) == ["review.completed"]
    assert event_types_for("verdict.submitted", {"result": "needs_human"}) == [
        "review.completed",
        "attention.required",
    ]


# ── formatting ───────────────────────────────────────────────────────────────


def test_format_event_message_blocks_and_fallback(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "OPENSWEEP_FRONTEND_BASE_URL", "https://opensweep.example")
    event = {
        "kind": "run.ended",
        "subject_type": "Run",
        "subject_uid": "run123",
        "actor_uid": "user1",
        "payload": {"playbook": "review"},
    }
    text, blocks = format_event_message(
        "run.completed", event, repo_slug="acme/api", subject_title="Review PR #7"
    )
    assert "Review PR #7" in text and "acme/api" in text
    assert blocks[0]["type"] == "section"
    assert "Run completed" in blocks[0]["text"]["text"]
    assert "review" in blocks[0]["text"]["text"]
    button = blocks[-1]["elements"][0]
    assert button["url"] == "https://opensweep.example/runs/run123"


def test_format_event_message_without_frontend_base(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "OPENSWEEP_FRONTEND_BASE_URL", "")
    monkeypatch.setattr(settings, "OPENSWEEP_WEBHOOK_PUBLIC_BASE_URL", "")
    _, blocks = format_event_message(
        "finding.created", {"subject_type": "Finding", "subject_uid": "f1", "payload": {}},
        repo_slug="", subject_title="",
    )
    assert all(b["type"] != "actions" for b in blocks)
    assert subject_link("Finding", "f1") == ""


def test_unknown_subject_type_gets_no_link(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "OPENSWEEP_FRONTEND_BASE_URL", "https://opensweep.example")
    assert subject_link("SlackConnection", "u1") == ""


def test_to_mrkdwn_conversions():
    src = "# Title\nSome **bold** and [a link](https://x.dev/page)\n`code` stays"
    out = to_mrkdwn(src)
    assert "*Title*" in out
    assert "*bold*" in out
    assert "<https://x.dev/page|a link>" in out
    assert "`code` stays" in out


def test_to_mrkdwn_truncates():
    out = to_mrkdwn("x" * 20000)
    assert len(out) < 8200
    assert "truncated" in out


# ── inbound parsing + repo resolution ────────────────────────────────────────


def test_parse_command():
    assert inbound.parse_command("") == ("help", "")
    assert inbound.parse_command("help") == ("help", "")
    assert inbound.parse_command("repos") == ("repos", "")
    assert inbound.parse_command("runs") == ("runs", "")
    assert inbound.parse_command("ask what is this repo?") == ("ask", "what is this repo?")
    assert inbound.parse_command("what is this repo?") == ("ask", "what is this repo?")


def test_strip_mentions():
    assert inbound.strip_mentions("<@U0123ABC> hello <@U0456DEF> world") == "hello  world"
    assert inbound.strip_mentions(None) == ""


def _repo(uid: str, slug: str) -> SimpleNamespace:
    return SimpleNamespace(uid=uid, slug=slug)


async def test_resolve_repository_explicit_token(monkeypatch):
    repos = [_repo("r1", "acme/api"), _repo("r2", "acme/web")]

    async def fake_repos(org_uid):
        return repos

    monkeypatch.setattr(inbound, "org_repositories", fake_repos)
    repo, question, err = await inbound.resolve_repository("o1", "repo:api how does auth work?")
    assert repo is repos[0] and err == ""
    assert question == "how does auth work?"


async def test_resolve_repository_single_repo_default(monkeypatch):
    repos = [_repo("r1", "acme/api")]

    async def fake_repos(org_uid):
        return repos

    monkeypatch.setattr(inbound, "org_repositories", fake_repos)
    repo, question, err = await inbound.resolve_repository("o1", "how does auth work?")
    assert repo is repos[0] and err == ""


async def test_resolve_repository_bare_mention(monkeypatch):
    repos = [_repo("r1", "acme/api"), _repo("r2", "acme/web")]

    async def fake_repos(org_uid):
        return repos

    monkeypatch.setattr(inbound, "org_repositories", fake_repos)
    repo, _, err = await inbound.resolve_repository("o1", "what does web's router do?")
    assert repo is repos[1] and err == ""


async def test_resolve_repository_ambiguous_asks_back(monkeypatch):
    repos = [_repo("r1", "acme/api"), _repo("r2", "acme/web")]

    async def fake_repos(org_uid):
        return repos

    monkeypatch.setattr(inbound, "org_repositories", fake_repos)
    repo, _, err = await inbound.resolve_repository("o1", "how does auth work?")
    assert repo is None
    assert "`acme/api`" in err and "`acme/web`" in err


async def test_resolve_repository_unknown_explicit_token(monkeypatch):
    async def fake_repos(org_uid):
        return [_repo("r1", "acme/api")]

    monkeypatch.setattr(inbound, "org_repositories", fake_repos)
    repo, _, err = await inbound.resolve_repository("o1", "repo:nope question")
    assert repo is None and "nope" in err


async def test_resolve_repository_no_repos(monkeypatch):
    async def fake_repos(org_uid):
        return []

    monkeypatch.setattr(inbound, "org_repositories", fake_repos)
    repo, _, err = await inbound.resolve_repository("o1", "hi")
    assert repo is None and "No repositories" in err


# ── audit-hook prefilter ─────────────────────────────────────────────────────


def _capture_send_task(monkeypatch):
    import celery_app

    calls = []

    def fake_send_task(name, kwargs=None, **_opts):
        calls.append((name, kwargs))

    monkeypatch.setattr(celery_app.app, "send_task", fake_send_task)
    return calls


def test_notify_enqueues_relevant_kind(monkeypatch):
    calls = _capture_send_task(monkeypatch)
    notify_slack_of_event(
        kind="ticket.created",
        subject_uid="t1",
        subject_type="Ticket",
        actor_uid="u1",
        repository_uid="repo1",
        payload={"title": "x"},
    )
    assert len(calls) == 1
    name, kwargs = calls[0]
    assert name == "opensweep.slack.deliver_event"
    assert kwargs["event"]["kind"] == "ticket.created"
    assert kwargs["event"]["repository_uid"] == "repo1"


def test_notify_skips_irrelevant_kind_and_platform_events(monkeypatch):
    calls = _capture_send_task(monkeypatch)
    notify_slack_of_event(
        kind="sandbox.created",  # not in the catalog map
        subject_uid="s1",
        subject_type="Sandbox",
        actor_uid="u1",
        repository_uid="repo1",
        payload={},
    )
    notify_slack_of_event(
        kind="ticket.created",  # relevant, but platform-level (no repo)
        subject_uid="t1",
        subject_type="Ticket",
        actor_uid="u1",
        repository_uid="",
        payload={},
    )
    assert calls == []


def test_notify_swallows_broker_errors(monkeypatch):
    import celery_app

    def boom(*_a, **_k):
        raise RuntimeError("broker down")

    monkeypatch.setattr(celery_app.app, "send_task", boom)
    # Must not raise — write_audit calls this on hot paths.
    notify_slack_of_event(
        kind="ticket.created",
        subject_uid="t1",
        subject_type="Ticket",
        actor_uid="u1",
        repository_uid="repo1",
        payload={},
    )


# ── inbound HTTP surface (signature gate + URL verification) ─────────────────


@pytest.fixture
def signed_client(monkeypatch):
    from fastapi.testclient import TestClient

    from app import app as fastapi_app
    from config import settings

    monkeypatch.setattr(settings, "SLACK_SIGNING_SECRET", SECRET)
    return TestClient(fastapi_app)


def _post_signed(client, path: str, body: bytes, secret: str = SECRET):
    ts = str(int(time.time()))
    return client.post(
        path,
        content=body,
        headers={
            "x-slack-request-timestamp": ts,
            "x-slack-signature": _sign(secret, int(ts), body),
            "content-type": "application/json",
        },
    )


def test_events_url_verification(signed_client):
    body = json.dumps({"type": "url_verification", "challenge": "c123"}).encode()
    res = _post_signed(signed_client, "/api/v1/slack/events", body)
    assert res.status_code == 200
    assert res.json() == {"challenge": "c123"}


def test_events_rejects_bad_signature(signed_client):
    body = json.dumps({"type": "url_verification", "challenge": "c123"}).encode()
    res = _post_signed(signed_client, "/api/v1/slack/events", body, secret="wrong")
    assert res.status_code == 403


def test_commands_reject_unsigned(signed_client):
    res = signed_client.post("/api/v1/slack/commands", content=b"text=help")
    assert res.status_code == 403


def test_slack_public_paths_are_auth_exempt():
    from app import TokenAuthMiddleware

    for path in (
        "/api/v1/slack/oauth/callback",
        "/api/v1/slack/events",
        "/api/v1/slack/commands",
    ):
        assert path in TokenAuthMiddleware.EXEMPT_PATHS
