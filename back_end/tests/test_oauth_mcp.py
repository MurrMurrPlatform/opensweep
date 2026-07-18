"""OAuth gateway for `opensweep connect` — pure logic + mounted surface.

PKCE verification, scope normalization, redirect-uri matching (exact +
RFC 8252 loopback port variance), token prefixes/hashing, and the public
endpoint + metadata surface.
"""

import base64
import hashlib

import pytest
from fastapi import HTTPException

from app import app
from domains.oauth_mcp.services.oauth_service import (
    ACCESS_TOKEN_PREFIX,
    CODE_PREFIX,
    REFRESH_TOKEN_PREFIX,
    hash_secret,
    mint_secret,
    normalize_scope,
    redirect_uri_allowed,
    scope_allows_write,
    verify_pkce_s256,
)


# ── PKCE ─────────────────────────────────────────────────────────────────────


def _challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )


def test_pkce_s256_roundtrip():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert verify_pkce_s256(verifier, _challenge(verifier))


def test_pkce_rejects_wrong_verifier():
    assert not verify_pkce_s256("wrong", _challenge("right"))


def test_pkce_rejects_empty():
    assert not verify_pkce_s256("", "")
    assert not verify_pkce_s256("v", "")


# ── Scopes ───────────────────────────────────────────────────────────────────


def test_scope_defaults_to_read():
    assert normalize_scope("") == "mcp:read"


def test_scope_accepts_known_and_dedupes():
    assert normalize_scope("mcp:read mcp:write mcp:read") == "mcp:read mcp:write"


def test_scope_rejects_unknown():
    with pytest.raises(HTTPException) as exc:
        normalize_scope("mcp:read admin:everything")
    assert exc.value.status_code == 400


def test_scope_write_predicate():
    assert scope_allows_write("mcp:read mcp:write")
    assert not scope_allows_write("mcp:read")


# ── Redirect URIs ────────────────────────────────────────────────────────────


def test_redirect_exact_match():
    assert redirect_uri_allowed("https://x/cb", ["https://x/cb"])
    assert not redirect_uri_allowed("https://evil/cb", ["https://x/cb"])


def test_redirect_loopback_port_variance():
    # RFC 8252 §7.3: loopback clients bind an ephemeral port per run.
    assert redirect_uri_allowed(
        "http://127.0.0.1:53171/callback", ["http://127.0.0.1:41999/callback"]
    )
    assert not redirect_uri_allowed(
        "http://127.0.0.1:53171/other", ["http://127.0.0.1:41999/callback"]
    )
    assert not redirect_uri_allowed(
        "http://10.0.0.5:53171/callback", ["http://10.0.0.5:41999/callback"]
    )


# ── Token shape ──────────────────────────────────────────────────────────────


def test_token_prefixes_are_distinct():
    assert len({ACCESS_TOKEN_PREFIX, REFRESH_TOKEN_PREFIX, CODE_PREFIX}) == 3


def test_minted_secrets_are_unique_and_prefixed():
    a, b = mint_secret(ACCESS_TOKEN_PREFIX), mint_secret(ACCESS_TOKEN_PREFIX)
    assert a != b and a.startswith(ACCESS_TOKEN_PREFIX)


def test_hash_is_stable_and_not_identity():
    assert hash_secret("x") == hash_secret("x")
    assert hash_secret("x") != "x"


# ── Mounted surface ──────────────────────────────────────────────────────────


def test_gateway_routes_are_mounted():
    paths = set(app.openapi().get("paths", {}).keys())
    assert "/.well-known/oauth-protected-resource" in paths
    assert "/.well-known/oauth-authorization-server" in paths
    assert "/oauth/register" in paths
    assert "/oauth/authorize" in paths
    assert "/oauth/token" in paths
    assert "/api/v1/oauth-mcp/approve" in paths


def test_public_endpoints_are_auth_exempt():
    from app import TokenAuthMiddleware

    for path in (
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-authorization-server",
        "/oauth/register",
        "/oauth/authorize",
        "/oauth/token",
    ):
        assert path in TokenAuthMiddleware.EXEMPT_PATHS, path
    # The consent endpoint must NOT be exempt — it requires the logged-in user.
    assert "/api/v1/oauth-mcp/approve" not in TokenAuthMiddleware.EXEMPT_PATHS
