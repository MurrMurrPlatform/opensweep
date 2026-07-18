"""OAuth 2.1 gateway for `opensweep connect` (unified dev flow, cloud auth).

MCP clients (Claude Code, Codex, OpenCode) speak OAuth to remote servers:
they discover metadata, dynamically register, run authorization-code + PKCE
in the user's browser, and refresh tokens themselves. Zitadel stays the only
place users authenticate — the gateway rides the SPA's existing OIDC login
for the consent step and mints its own opaque, hashed, org-scoped tokens.

Secrets are NEVER stored: every code/token column holds a SHA-256 hash.
Access tokens (`osmcp_…`) are short-lived; refresh tokens (`osmcr_…`)
are single-use and rotate on every refresh.
"""

from neomodel import (
    AsyncStructuredNode,
    DateTimeProperty,
    JSONProperty,
    StringProperty,
)


class OAuthClient(AsyncStructuredNode):
    """A dynamically registered MCP client (RFC 7591). Public client — PKCE
    only, no secret."""

    uid = StringProperty(unique_index=True, required=True)  # client_id
    name = StringProperty(default="")
    redirect_uris = JSONProperty(default=[])
    created_at = DateTimeProperty(default_now=True)


class OAuthCode(AsyncStructuredNode):
    """Single-use authorization code, bound to user + client + PKCE challenge."""

    uid = StringProperty(unique_index=True, required=True)
    code_hash = StringProperty(unique_index=True, required=True)
    client_id = StringProperty(required=True, index=True)
    user_uid = StringProperty(required=True)
    scope = StringProperty(default="mcp:read")
    code_challenge = StringProperty(required=True)  # S256 only
    redirect_uri = StringProperty(required=True)
    expires_at = DateTimeProperty()
    used_at = DateTimeProperty()
    created_at = DateTimeProperty(default_now=True)


class OAuthToken(AsyncStructuredNode):
    """An access/refresh token pair. Refresh rotation: exchanging the refresh
    token revokes this pair and mints a successor (`rotated_to`)."""

    uid = StringProperty(unique_index=True, required=True)
    access_hash = StringProperty(unique_index=True, required=True)
    refresh_hash = StringProperty(unique_index=True, required=True)
    client_id = StringProperty(required=True, index=True)
    user_uid = StringProperty(required=True, index=True)
    scope = StringProperty(default="mcp:read")
    access_expires_at = DateTimeProperty()
    refresh_expires_at = DateTimeProperty()
    revoked_at = DateTimeProperty()
    rotated_to = StringProperty(default="")
    last_used_at = DateTimeProperty()
    created_at = DateTimeProperty(default_now=True)


OAUTH_SCOPES = {"mcp:read", "mcp:write"}
