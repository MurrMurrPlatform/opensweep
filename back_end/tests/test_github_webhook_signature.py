"""Webhook signature verification — fails closed, constant-time."""

import hashlib
import hmac

from infrastructure.github_webhook import verify_signature

SECRET = "topsecret"
BODY = b'{"action": "opened"}'


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_accepted():
    assert verify_signature(secret=SECRET, body=BODY, signature_header=_sign(SECRET, BODY))


def test_wrong_secret_rejected():
    assert not verify_signature(secret=SECRET, body=BODY, signature_header=_sign("other", BODY))


def test_tampered_body_rejected():
    assert not verify_signature(secret=SECRET, body=b'{"action":"closed"}', signature_header=_sign(SECRET, BODY))


def test_missing_header_rejected():
    assert not verify_signature(secret=SECRET, body=BODY, signature_header=None)
    assert not verify_signature(secret=SECRET, body=BODY, signature_header="")


def test_unset_secret_fails_closed():
    # An unconfigured GITHUB_WEBHOOK_SECRET must never accept anything.
    assert not verify_signature(secret="", body=BODY, signature_header=_sign("", BODY))


def test_wrong_scheme_rejected():
    sha1 = "sha1=" + hmac.new(SECRET.encode(), BODY, hashlib.sha1).hexdigest()
    assert not verify_signature(secret=SECRET, body=BODY, signature_header=sha1)
