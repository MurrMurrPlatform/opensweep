"""Shared HMAC key for OAuth-ish state nonces (GitHub App, Slack).

One precedence chain for every signed browser-redirect state so operators
configure a single secret: dedicated OPENSWEEP_STATE_SIGNING_SECRET, then the
run-token secret chain (OPENSWEEP_RUN_TOKEN_SECRET → OPENSWEEP_AUTH_TOKEN), then a
process-lifetime random secret (auth-disabled local dev — the redirect lands
on the same process within the state's expiry window).
"""

from __future__ import annotations

import secrets as pysecrets

from config import settings
from logging_config import logger

_ephemeral_secret = pysecrets.token_hex(32)

_warned_fallback = False
_warned_ephemeral = False


def state_secret() -> str:
    """The HMAC key used to sign state nonces."""
    global _warned_fallback, _warned_ephemeral
    dedicated = (settings.OPENSWEEP_STATE_SIGNING_SECRET or "").strip()
    if dedicated:
        return dedicated

    from infrastructure.run_tokens import _secret

    fallback = _secret()
    if fallback:
        if not _warned_fallback:
            _warned_fallback = True
            logger.warning(
                "state nonce signing is using OPENSWEEP_RUN_TOKEN_SECRET/"
                "OPENSWEEP_AUTH_TOKEN as fallback — set a dedicated "
                "OPENSWEEP_STATE_SIGNING_SECRET",
                extra={"tag": "auth"},
            )
        return fallback
    if not _warned_ephemeral:
        _warned_ephemeral = True
        logger.warning(
            "state nonce signing is using a process-lifetime ephemeral secret "
            "(no signing secret configured) — install flows break across "
            "replicas/restarts; set OPENSWEEP_STATE_SIGNING_SECRET",
            extra={"tag": "auth"},
        )
    return _ephemeral_secret
