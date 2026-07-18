"""OAuth gateway logic — pure helpers + node lifecycle.

Pure parts (PKCE verification, token minting/hashing, scope parsing,
redirect-uri matching) carry the tests; the async service functions are thin
node plumbing around them.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException

from domains.oauth_mcp.models import OAUTH_SCOPES, OAuthClient, OAuthCode, OAuthToken
from infrastructure.audit import write_audit

ACCESS_TOKEN_PREFIX = "osmcp_"
REFRESH_TOKEN_PREFIX = "osmcr_"
CODE_PREFIX = "osmcc_"

ACCESS_TTL = timedelta(hours=1)
REFRESH_TTL = timedelta(days=90)
CODE_TTL = timedelta(minutes=10)

DEFAULT_SCOPE = "mcp:read"


# ── Pure helpers ─────────────────────────────────────────────────────────────


def hash_secret(value: str) -> str:
    return hashlib.sha256((value or "").encode()).hexdigest()


def mint_secret(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(32)


def verify_pkce_s256(verifier: str, challenge: str) -> bool:
    """RFC 7636 S256: BASE64URL(SHA256(verifier)) == challenge."""
    if not verifier or not challenge:
        return False
    digest = hashlib.sha256(verifier.encode("ascii", errors="replace")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(computed, challenge)


def normalize_scope(requested: str) -> str:
    """Intersect the request with the supported scopes; empty → default.
    Unknown scopes are rejected, not silently dropped, so a client asking for
    more than we grant finds out at authorize time."""
    parts = [s for s in (requested or "").split() if s]
    if not parts:
        return DEFAULT_SCOPE
    unknown = [s for s in parts if s not in OAUTH_SCOPES]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unsupported scope: {' '.join(unknown)}")
    return " ".join(dict.fromkeys(parts))


def redirect_uri_allowed(redirect_uri: str, registered: list[str]) -> bool:
    """Exact-match against the registered list (OAuth 2.1 — no wildcards).
    Loopback redirects (RFC 8252 §7.3) may vary the PORT only."""
    if not redirect_uri:
        return False
    if redirect_uri in registered:
        return True
    from urllib.parse import urlparse

    try:
        presented = urlparse(redirect_uri)
    except ValueError:
        return False
    if presented.hostname not in {"127.0.0.1", "::1", "localhost"}:
        return False
    for r in registered:
        try:
            reg = urlparse(r)
        except ValueError:
            continue
        if (
            reg.hostname == presented.hostname
            and reg.scheme == presented.scheme
            and reg.path == presented.path
        ):
            return True
    return False


def scope_allows_write(scope: str) -> bool:
    return "mcp:write" in (scope or "").split()


# ── Node lifecycle ───────────────────────────────────────────────────────────


async def register_client(*, name: str, redirect_uris: list[str]) -> OAuthClient:
    if not redirect_uris:
        raise HTTPException(status_code=400, detail="redirect_uris is required")
    client = OAuthClient(
        uid=uuid4().hex, name=(name or "")[:120], redirect_uris=redirect_uris[:10]
    )
    await client.save()
    await write_audit(
        kind="oauth_client.registered",
        subject_uid=client.uid,
        subject_type="OAuthClient",
        actor_uid="anonymous",
        payload={"name": client.name, "redirect_uris": redirect_uris[:10]},
    )
    return client


async def get_client(client_id: str) -> OAuthClient:
    client = await OAuthClient.nodes.get_or_none(uid=(client_id or "").strip())
    if client is None:
        raise HTTPException(status_code=400, detail="unknown client_id")
    return client


async def issue_code(
    *,
    client: OAuthClient,
    user_uid: str,
    scope: str,
    code_challenge: str,
    redirect_uri: str,
) -> str:
    code = mint_secret(CODE_PREFIX)
    now = datetime.now(UTC)
    node = OAuthCode(
        uid=uuid4().hex,
        code_hash=hash_secret(code),
        client_id=client.uid,
        user_uid=user_uid,
        scope=scope,
        code_challenge=code_challenge,
        redirect_uri=redirect_uri,
        expires_at=now + CODE_TTL,
    )
    await node.save()
    return code


async def exchange_code(
    *, code: str, client_id: str, redirect_uri: str, code_verifier: str
) -> OAuthToken:
    node = await OAuthCode.nodes.get_or_none(code_hash=hash_secret(code or ""))
    now = datetime.now(UTC)
    if (
        node is None
        or node.used_at is not None
        or (node.expires_at and node.expires_at < now)
        or node.client_id != (client_id or "").strip()
        or node.redirect_uri != (redirect_uri or "")
    ):
        raise HTTPException(status_code=400, detail="invalid_grant")
    if not verify_pkce_s256(code_verifier, node.code_challenge):
        raise HTTPException(status_code=400, detail="invalid_grant")
    node.used_at = now
    await node.save()
    return await _mint_token_pair(
        client_id=node.client_id, user_uid=node.user_uid, scope=node.scope
    )


async def refresh_tokens(*, refresh_token: str, client_id: str) -> OAuthToken:
    node = await OAuthToken.nodes.get_or_none(refresh_hash=hash_secret(refresh_token or ""))
    now = datetime.now(UTC)
    if (
        node is None
        or node.revoked_at is not None
        or node.client_id != (client_id or "").strip()
        or (node.refresh_expires_at and node.refresh_expires_at < now)
    ):
        raise HTTPException(status_code=400, detail="invalid_grant")
    successor = await _mint_token_pair(
        client_id=node.client_id, user_uid=node.user_uid, scope=node.scope
    )
    node.revoked_at = now
    node.rotated_to = successor.uid
    await node.save()
    return successor


async def _mint_token_pair(*, client_id: str, user_uid: str, scope: str) -> OAuthToken:
    now = datetime.now(UTC)
    access = mint_secret(ACCESS_TOKEN_PREFIX)
    refresh = mint_secret(REFRESH_TOKEN_PREFIX)
    node = OAuthToken(
        uid=uuid4().hex,
        access_hash=hash_secret(access),
        refresh_hash=hash_secret(refresh),
        client_id=client_id,
        user_uid=user_uid,
        scope=scope,
        access_expires_at=now + ACCESS_TTL,
        refresh_expires_at=now + REFRESH_TTL,
    )
    await node.save()
    # The cleartext values leave the process exactly once, on this response.
    node._access_token = access  # noqa: SLF001 — transient, not persisted
    node._refresh_token = refresh  # noqa: SLF001
    return node


async def resolve_access_token(token: str) -> OAuthToken | None:
    """Middleware path: cleartext access token → live token node, or None."""
    if not (token or "").startswith(ACCESS_TOKEN_PREFIX):
        return None
    node = await OAuthToken.nodes.get_or_none(access_hash=hash_secret(token))
    if node is None or node.revoked_at is not None:
        return None
    now = datetime.now(UTC)
    if node.access_expires_at and node.access_expires_at < now:
        return None
    if node.last_used_at is None or (now - node.last_used_at) > timedelta(minutes=5):
        node.last_used_at = now
        await node.save()
    return node
