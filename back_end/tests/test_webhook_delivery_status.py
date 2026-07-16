"""Webhook delivery status lifecycle — failed deliveries are NOT permanently
dropped (redelivery reprocesses them); succeeded ones stay duplicates.

Covers the pure disposition function plus the full endpoint flow with a fake
WebhookDelivery store (no Neo4j).
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

import api.v1.github_webhooks as gw
from api.v1.github_webhooks import STALE_PROCESSING_AFTER, delivery_disposition

NOW = datetime(2026, 7, 9, 12, 0, 0, tzinfo=UTC)


# ── Pure disposition ─────────────────────────────────────────────────────────


def test_unseen_delivery_is_new():
    assert delivery_disposition(status=None, updated_at=None, now=NOW) == "new"


def test_succeeded_delivery_is_duplicate():
    assert delivery_disposition(status="succeeded", updated_at=NOW, now=NOW) == "duplicate"


def test_failed_delivery_is_reprocessed():
    # The core fix: a failed "PR merged" event must not be dropped forever.
    assert delivery_disposition(status="failed", updated_at=NOW, now=NOW) == "reprocess"


def test_inflight_processing_is_duplicate():
    recent = NOW - timedelta(minutes=1)
    assert delivery_disposition(status="processing", updated_at=recent, now=NOW) == "duplicate"


def test_stale_processing_is_reprocessed():
    # Worker died mid-flight >5 min ago — redelivery must run again.
    stale = NOW - STALE_PROCESSING_AFTER - timedelta(seconds=1)
    assert delivery_disposition(status="processing", updated_at=stale, now=NOW) == "reprocess"


def test_processing_without_timestamp_is_reprocessed():
    assert delivery_disposition(status="processing", updated_at=None, now=NOW) == "reprocess"


# ── Endpoint flow with a fake store ──────────────────────────────────────────


class FakeDelivery:
    store: dict = {}

    def __init__(self, delivery_id, event="", action=""):
        self.delivery_id = delivery_id
        self.event = event
        self.action = action
        self.status = "processing"
        self.attempts = 0
        self.received_at = datetime.now(UTC)
        self.updated_at = None

    async def save(self):
        FakeDelivery.store[self.delivery_id] = self

    class nodes:
        @staticmethod
        async def get_or_none(delivery_id):
            return FakeDelivery.store.get(delivery_id)


class FakeRequest:
    def __init__(self, event="pull_request", delivery_id="d-1"):
        self.headers = {
            "X-GitHub-Event": event,
            "X-GitHub-Delivery": delivery_id,
            "X-Hub-Signature-256": "sha256=stub",
        }
        self._body = json.dumps({"action": "closed"}).encode()

    async def body(self):
        return self._body

    async def json(self):
        return json.loads(self._body)


async def fake_claim(*, delivery_id, event, action, now):
    """Store-backed stand-in for the atomic Cypher claim — same disposition
    rules, applied against FakeDelivery.store."""
    d = FakeDelivery.store.get(delivery_id)
    disposition = delivery_disposition(
        status=(d.status or "succeeded") if d is not None else None,
        updated_at=(d.updated_at or d.received_at) if d is not None else None,
        now=now,
    )
    if disposition == "duplicate":
        return False
    if d is None:
        d = FakeDelivery(delivery_id, event=event, action=action)
    d.status = "processing"
    d.attempts = int(d.attempts or 0) + 1
    d.updated_at = now
    await d.save()
    return True


@pytest.fixture()
def webhook_env(monkeypatch):
    FakeDelivery.store = {}
    calls = {"process": 0}
    monkeypatch.setattr(gw, "WebhookDelivery", FakeDelivery)
    monkeypatch.setattr(gw, "_claim_delivery", fake_claim)
    monkeypatch.setattr(gw, "verify_signature", lambda **_kw: True)

    async def ok_process(*, event, action, payload):
        calls["process"] += 1
        return {"ok": True, "event": event, "action": action, "synced": []}

    monkeypatch.setattr(gw, "_process_delivery", ok_process)
    return calls


async def test_success_marks_delivery_succeeded(webhook_env):
    out = await gw.github_webhook(FakeRequest())
    assert out["ok"] is True
    d = FakeDelivery.store["d-1"]
    assert d.status == "succeeded"
    assert d.attempts == 1
    assert webhook_env["process"] == 1


async def test_succeeded_redelivery_is_noop(webhook_env):
    await gw.github_webhook(FakeRequest())
    out = await gw.github_webhook(FakeRequest())
    assert out.get("duplicate") is True
    assert webhook_env["process"] == 1  # not processed twice


async def test_failure_marks_failed_and_returns_500(webhook_env, monkeypatch):
    async def boom(*, event, action, payload):
        raise RuntimeError("sync exploded")

    monkeypatch.setattr(gw, "_process_delivery", boom)
    with pytest.raises(HTTPException) as exc_info:
        await gw.github_webhook(FakeRequest())
    assert exc_info.value.status_code == 500  # GitHub will redeliver
    d = FakeDelivery.store["d-1"]
    assert d.status == "failed"
    assert d.attempts == 1


async def test_failed_delivery_is_reprocessed_on_redelivery(webhook_env, monkeypatch):
    async def boom(*, event, action, payload):
        raise RuntimeError("sync exploded")

    monkeypatch.setattr(gw, "_process_delivery", boom)
    with pytest.raises(HTTPException):
        await gw.github_webhook(FakeRequest())

    # GitHub redelivers; processing now succeeds.
    async def ok_process(*, event, action, payload):
        webhook_env["process"] += 1
        return {"ok": True, "event": event, "action": action, "synced": [7]}

    monkeypatch.setattr(gw, "_process_delivery", ok_process)
    out = await gw.github_webhook(FakeRequest())
    assert out["synced"] == [7]
    d = FakeDelivery.store["d-1"]
    assert d.status == "succeeded"
    assert d.attempts == 2


async def test_inflight_delivery_is_not_double_processed(webhook_env):
    d = FakeDelivery("d-1", event="pull_request")
    d.status = "processing"
    d.attempts = 1
    d.updated_at = datetime.now(UTC)  # fresh — another worker is on it
    FakeDelivery.store["d-1"] = d
    out = await gw.github_webhook(FakeRequest())
    assert out.get("duplicate") is True
    assert webhook_env["process"] == 0


async def test_stale_processing_delivery_is_reprocessed(webhook_env):
    d = FakeDelivery("d-1", event="pull_request")
    d.status = "processing"
    d.attempts = 1
    d.updated_at = datetime.now(UTC) - timedelta(minutes=10)  # orphaned
    FakeDelivery.store["d-1"] = d
    out = await gw.github_webhook(FakeRequest())
    assert out["ok"] is True
    assert webhook_env["process"] == 1
    assert FakeDelivery.store["d-1"].status == "succeeded"
    assert FakeDelivery.store["d-1"].attempts == 2
