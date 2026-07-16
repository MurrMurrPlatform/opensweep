"""GitHub webhook signature verification — pure helper, unit-testable."""

import hashlib
import hmac


def verify_signature(*, secret: str, body: bytes, signature_header: str | None) -> bool:
    """Validate an X-Hub-Signature-256 header against the raw request body.

    Constant-time comparison; missing secret or header always fails closed.
    """
    if not secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)
