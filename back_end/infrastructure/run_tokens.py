"""Per-run scoped tokens for the executor → platform callback surface (§13).

Agents must be able to call back into the platform-tool MCP mount, but they
must never hold the platform-wide OPENSWEEP_AUTH_TOKEN (anything the agent can
read, the code it analyzes can exfiltrate). Instead each run gets a derived
token bound to its run uid:

    osrt_<hmac_sha256(secret, run_uid)[:40]>

TokenAuthMiddleware accepts these ONLY on the platform-tool callback paths
(/mcp/platform, /api/v1/platform-tools) and validates them statelessly by
recomputing from the `X-OpenSweep-Run-Uid` header — no storage, no expiry
bookkeeping (the token is worthless outside the tool surface and only valid
together with its own run uid).

The HMAC secret is OPENSWEEP_AUTH_TOKEN; deployments that want to rotate the
platform token without invalidating in-flight runs can pin a dedicated
OPENSWEEP_RUN_TOKEN_SECRET instead (checked first).
"""

from __future__ import annotations

import hashlib
import hmac
import os

RUN_TOKEN_PREFIX = "osrt_"
_DIGEST_LEN = 40


def _secret() -> str:
    """HMAC key: dedicated OPENSWEEP_RUN_TOKEN_SECRET when set, else the shared
    OPENSWEEP_AUTH_TOKEN. Empty when auth is disabled (no tokens minted)."""
    dedicated = os.environ.get("OPENSWEEP_RUN_TOKEN_SECRET", "").strip()
    if dedicated:
        return dedicated
    try:
        from config import settings

        return (getattr(settings, "OPENSWEEP_AUTH_TOKEN", "") or "").strip()
    except Exception:
        return ""


def mint_run_token(run_uid: str) -> str:
    """Derive the scoped token for one run. Empty when auth is disabled or
    run_uid is missing (callers then send no auth header — current behavior)."""
    secret = _secret()
    if not run_uid or not secret:
        return ""
    digest = hmac.new(secret.encode(), run_uid.encode(), hashlib.sha256).hexdigest()
    return RUN_TOKEN_PREFIX + digest[:_DIGEST_LEN]


def run_token_config_error() -> str:
    """"" when executor callbacks can authenticate (or auth is off entirely);
    else a diagnostic explaining the config gap.

    TokenAuthMiddleware enforces auth when OPENSWEEP_AUTH_TOKEN **or**
    ZITADEL_ISSUER is set, but run tokens can only be minted from
    OPENSWEEP_RUN_TOKEN_SECRET or OPENSWEEP_AUTH_TOKEN. A Zitadel-only deployment
    without a run-token secret therefore 401s every executor MCP callback —
    the server "connects" (SSE endpoint reachable) yet lists zero tools.
    """
    try:
        from config import settings

        oidc_on = bool((getattr(settings, "ZITADEL_ISSUER", "") or "").strip())
    except Exception:
        oidc_on = False
    if not oidc_on or _secret():
        return ""
    return (
        "auth is enforced (ZITADEL_ISSUER is set) but no run-token secret is "
        "configured — set OPENSWEEP_RUN_TOKEN_SECRET (or OPENSWEEP_AUTH_TOKEN) on the "
        "backend AND worker so executor MCP callbacks can authenticate"
    )


def verify_run_token(token: str, run_uid: str) -> bool:
    """Constant-time check that `token` is the minted token for `run_uid`."""
    if not token or not run_uid or not token.startswith(RUN_TOKEN_PREFIX):
        return False
    expected = mint_run_token(run_uid)
    if not expected:
        return False
    return hmac.compare_digest(token.encode(), expected.encode())
