"""Slack request signing + install-state nonces.

Inbound requests (Events API, slash commands) carry Slack's v0 signature:
    X-Slack-Signature: v0=HMAC_SHA256(signing_secret, f"v0:{ts}:{body}")
    X-Slack-Request-Timestamp: unix seconds (reject when older than 5 min).

The install state (`sls_…`) binds an OAuth v2 install to the OpenSweep org that
started it — the same signed-nonce pattern as the GitHub App install flow
(api/v1/github_app.py), sharing the key from infrastructure/state_signing.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets as pysecrets
import time

SIGNATURE_MAX_AGE_SECONDS = 300  # Slack's documented replay window

STATE_PREFIX = "sls_"
STATE_MAX_AGE_SECONDS = 3600  # picking channels/authorizing can take a while


def verify_slack_signature(
    *,
    signing_secret: str,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
    now: int | None = None,
) -> bool:
    """Constant-time v0 signature check with the 5-minute replay window."""
    if not signing_secret or not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    current = int(now if now is not None else time.time())
    if abs(current - ts) > SIGNATURE_MAX_AGE_SECONDS:
        return False
    base = b"v0:" + timestamp.encode() + b":" + body
    expected = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), signature.encode())


def _state_key() -> str:
    from infrastructure.state_signing import state_secret

    return state_secret()


def _sign_state(ts: int, org_uid: str, user_uid: str, nonce: str) -> str:
    digest = hmac.new(
        _state_key().encode(),
        f"slack.{ts}.{org_uid}.{user_uid}.{nonce}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return digest[:40]


def mint_install_state(org_uid: str, user_uid: str = "", *, now: int | None = None) -> str:
    """`sls_{ts}.{org_uid}.{user_uid}.{nonce}.{sig}` — org/user uids never
    contain `.`. user_uid records who started the install (the callback is an
    unauthenticated browser redirect, so the state is the only carrier)."""
    ts = int(now if now is not None else time.time())
    nonce = pysecrets.token_hex(8)
    sig = _sign_state(ts, org_uid, user_uid, nonce)
    return f"{STATE_PREFIX}{ts}.{org_uid}.{user_uid}.{nonce}.{sig}"


def verify_install_state(state: str, *, now: int | None = None) -> tuple[str, str]:
    """(org_uid, user_uid) the state was minted for, or ("", "") when
    invalid/expired."""
    invalid = ("", "")
    if not state or not state.startswith(STATE_PREFIX):
        return invalid
    parts = state[len(STATE_PREFIX):].split(".")
    if len(parts) != 5:
        return invalid
    raw_ts, org_uid, user_uid, nonce, sig = parts
    try:
        ts = int(raw_ts)
    except ValueError:
        return invalid
    current = int(now if now is not None else time.time())
    if not (0 <= current - ts <= STATE_MAX_AGE_SECONDS):
        return invalid
    if not hmac.compare_digest(sig.encode(), _sign_state(ts, org_uid, user_uid, nonce).encode()):
        return invalid
    return org_uid, user_uid
