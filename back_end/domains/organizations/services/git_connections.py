"""Per-org PAT git connections — the self-serve path for self-hosters.

An org owner pastes a (fine-grained) GitHub personal access token; it becomes
a GitConnection(kind="pat") sealed at rest. Repos the token can reach are
browsable next to GitHub App installations in the connect dialog, and repos
registered through it authenticate with that token (see
infrastructure/github_app.get_repo_git_token — precedence: installation
token → connection PAT → global env PAT).

The GitHub App (scripts/github-app-setup.sh) stays the recommended
production path; PAT connections exist so `docker compose up` + paste-a-token
is a complete setup — no App creation, no public URL required.

`ensure_env_pat_connection` is the zero-step variant: a GITHUB_TOKEN already
present in the environment is auto-connected to the platform admin's org on
their first login (api resolve path), so a .env-configured instance needs no
UI step at all.
"""

from __future__ import annotations

import hashlib
from typing import Any

import httpx

from config import settings
from domains.organizations.models import GitConnection
from infrastructure import secretbox
from infrastructure.audit import write_audit
from logging_config import logger

_GITHUB_API = "https://api.github.com"

# Defensive cap when listing a token's repositories — discovery only needs
# enough for a selection UI (mirrors github_app.MAX_INSTALLATION_REPOS).
MAX_PAT_REPOS = 300


class PatValidationError(Exception):
    """Token rejected by GitHub (bad/expired/insufficient) — a 4xx cause the
    caller can show verbatim. Network trouble raises httpx errors instead."""


def token_fingerprint(token: str) -> str:
    """external_id for a PAT connection: stable digest, never the token."""
    return "pat:" + hashlib.sha256(token.encode()).hexdigest()[:32]


def _seal(token: str) -> str:
    """Sealed when OPENSWEEP_SECRETS_KEY is configured; plaintext otherwise
    (dev without a key) — unseal() passes plaintext through unchanged."""
    return secretbox.seal(token) if secretbox.configured() else token


def connection_token(conn: GitConnection) -> str:
    """The plaintext PAT of a kind="pat" connection ("" when undecryptable —
    the operator lost OPENSWEEP_SECRETS_KEY; callers treat it as no-credential)."""
    try:
        return secretbox.unseal(conn.token_sealed or "")
    except secretbox.SecretBoxError as exc:
        logger.error(
            f"git connection {conn.uid} token cannot be decrypted: {exc}",
            extra={"tag": "github"},
        )
        return ""


async def validate_pat(token: str) -> dict:
    """GET /user with the token — the authenticating identity. Raises
    PatValidationError on 4xx (bad token), httpx errors on network trouble."""
    async with httpx.AsyncClient(base_url=_GITHUB_API, timeout=15) as client:
        r = await client.get(
            "/user",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    if r.status_code in (401, 403):
        raise PatValidationError("GitHub rejected the token (expired, revoked, or wrong scopes)")
    if r.status_code >= 400:
        raise PatValidationError(f"GitHub returned {r.status_code} validating the token")
    body = r.json()
    return body if isinstance(body, dict) else {}


async def create_pat_connection(
    *, org_uid: str, token: str, linked_by: str = ""
) -> GitConnection:
    """Validate the token against GitHub and store it as an org connection.

    Idempotent for the same org (re-pasting the same token returns the
    existing connection); the same token in ANOTHER org is refused without
    revealing whose it is (mirrors link_installation's first-org-wins)."""
    token = (token or "").strip()
    if not token:
        raise PatValidationError("token is empty")

    fingerprint = token_fingerprint(token)
    existing = await GitConnection.nodes.get_or_none(external_id=fingerprint)
    if existing is not None:
        if existing.org_uid == org_uid:
            return existing
        raise PatValidationError("this token is already connected")

    identity = await validate_pat(token)
    login = str(identity.get("login") or "")
    conn = await GitConnection(
        org_uid=org_uid,
        provider="github",
        kind="pat",
        external_id=fingerprint,
        display_name=login,
        token_sealed=_seal(token),
        linked_by=linked_by,
    ).save()
    await write_audit(
        kind="git_connection.pat_added",
        subject_uid=conn.uid,
        subject_type="GitConnection",
        actor_uid=linked_by or "operator",
        payload={"org_uid": org_uid, "account": login},
    )
    return conn


async def org_pat_connections(org_uid: str) -> list[GitConnection]:
    return await GitConnection.nodes.filter(org_uid=org_uid, kind="pat")


async def delete_pat_connection(uid: str, org_uid: str, *, actor_uid: str = "") -> bool:
    """Remove one of the org's PAT connections. Repos registered through it
    keep their git_connection_uid and fall back to the global env PAT (or
    fail visibly) — same posture as an uninstalled App installation."""
    conn = await GitConnection.nodes.get_or_none(uid=uid, org_uid=org_uid, kind="pat")
    if conn is None:
        return False
    await conn.delete()
    await write_audit(
        kind="git_connection.pat_removed",
        subject_uid=uid,
        subject_type="GitConnection",
        actor_uid=actor_uid or "operator",
        payload={"org_uid": org_uid},
    )
    return True


async def list_pat_repos(token: str) -> list[dict]:
    """Repositories the token can access — raw GitHub repo dicts from
    GET /user/repos (paginated, capped at MAX_PAT_REPOS). Fine-grained PATs
    return exactly the repos the token was granted. Raises on failure."""
    repos: list[dict] = []
    async with httpx.AsyncClient(base_url=_GITHUB_API, timeout=15) as client:
        url: str | None = "/user/repos?per_page=100&sort=updated"
        while url and len(repos) < MAX_PAT_REPOS:
            r = await client.get(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            r.raise_for_status()
            body = r.json()
            repos.extend(p for p in (body or []) if isinstance(p, dict))
            url = (r.links.get("next") or {}).get("url")
    return repos[:MAX_PAT_REPOS]


# ── Env-token auto-connect (zero-step OSS setup) ─────────────────────────────

# Once the instance-level decision is made (connected, or "there are already
# connections — the operator chose"), skip the DB probe on later logins.
_env_seed_settled = False


def _reset_env_seed_flag() -> None:  # test hook
    global _env_seed_settled
    _env_seed_settled = False


async def ensure_env_pat_connection(org_uid: str, *, linked_by: str = "") -> None:
    """First platform-admin login on a fresh instance: a GITHUB_TOKEN already
    configured in the environment becomes that org's PAT connection, so a
    .env-based setup needs no UI step. Strictly best-effort and one-shot:
    any existing connection means the operator already chose — do nothing.

    Never raises — a GitHub/DB hiccup only defers seeding to a later login.
    """
    global _env_seed_settled
    token = (settings.GITHUB_TOKEN or "").strip()
    if not token or _env_seed_settled:
        return
    try:
        if await GitConnection.nodes.all():
            _env_seed_settled = True
            return
        conn = await create_pat_connection(org_uid=org_uid, token=token, linked_by=linked_by)
        _env_seed_settled = True
        logger.info(
            f"auto-connected env GITHUB_TOKEN as PAT connection {conn.uid} "
            f"for org {org_uid} (account {conn.display_name or '?'})",
            extra={"tag": "github"},
        )
    except PatValidationError as exc:
        # A bad env token stays bad — settle so we don't re-probe forever.
        _env_seed_settled = True
        logger.warning(f"env GITHUB_TOKEN auto-connect refused: {exc}", extra={"tag": "github"})
    except Exception as exc:  # noqa: BLE001 — network/DB trouble: retry on a later login
        logger.warning(f"env GITHUB_TOKEN auto-connect deferred: {exc}", extra={"tag": "github"})


# ── Best-effort repo webhook (PAT-registered repos) ──────────────────────────

WEBHOOK_EVENTS = ["pull_request", "check_suite", "check_run", "push"]


def _webhook_url() -> str:
    """The public webhook receiver URL, or "" when the instance has no
    GitHub-reachable origin (localhost dev) or no webhook secret configured
    (the receiver fails closed without one — a hook would be pure noise)."""
    base = (settings.OPENSWEEP_WEBHOOK_PUBLIC_BASE_URL or "").rstrip("/")
    if not base or not settings.GITHUB_WEBHOOK_SECRET:
        return ""
    host = httpx.URL(base).host or ""
    if host in ("localhost", "127.0.0.1"):
        return ""
    return f"{base}/api/v1/github/webhook"


async def maybe_create_repo_webhook(*, token: str, owner: str, name: str) -> bool:
    """Create the OpenSweep webhook on one repo with the connection's token —
    what the App's built-in webhook does for installation repos. Best-effort:
    False (never an exception) when the instance isn't publicly reachable,
    the token lacks webhook permission, or the hook already exists."""
    url = _webhook_url()
    if not url:
        return False
    try:
        async with httpx.AsyncClient(base_url=_GITHUB_API, timeout=15) as client:
            r = await client.post(
                f"/repos/{owner}/{name}/hooks",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json={
                    "config": {
                        "url": url,
                        "content_type": "json",
                        "secret": settings.GITHUB_WEBHOOK_SECRET,
                    },
                    "events": WEBHOOK_EVENTS,
                    "active": True,
                },
            )
        if r.status_code == 201:
            return True
        # 422 = hook already exists for this URL — fine. Anything else
        # (403 no permission, 404 no admin access) just means polling mode.
        if r.status_code != 422:
            logger.info(
                f"webhook create on {owner}/{name} skipped: {r.status_code} {r.text[:120]}",
                extra={"tag": "github"},
            )
        return False
    except Exception as exc:  # noqa: BLE001
        logger.info(f"webhook create on {owner}/{name} failed: {exc}", extra={"tag": "github"})
        return False


def connection_summary(conn: GitConnection) -> dict[str, Any]:
    """Secret-free API view."""
    return {
        "uid": conn.uid,
        "kind": conn.kind or "app",
        "account": conn.display_name or "",
        "created_at": conn.created_at.isoformat() if conn.created_at else "",
    }
