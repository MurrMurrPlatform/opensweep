"""GitHub App installation flow (§7) — install → link → register.

The App itself is DEPLOYMENT CONFIG: created once per environment by
scripts/github-app-setup.sh (GitHub's manifest flow needs one browser
click; the script captures the credentials) and read from the environment via
infrastructure/github_app_store.py. There is no in-platform creation flow.

What stays in the platform is the per-org runtime linking:

  1. Any org user opens install_url (from /status or /available-repos) — the
     URL carries a signed install state binding the flow to their org — and
     installs the App on their GitHub account/org (one App supports multiple
     installations).
  2. GitHub redirects their browser to GET /api/v1/github/app/setup with the
     installation id + the state; the installation is linked to that org
     (first org wins; never re-pointed).
  3. GET /available-repos lists every repo the org's installations grant
     access to (cross-matched against registered Repository nodes) and
     POST /register-repo registers ONE selected repo. The `installation` /
     `installation_repositories` webhooks never create repos — they only
     link/unlink installations onto registered ones.

/setup is exempt from TokenAuthMiddleware (app.py) — GitHub redirects a plain
browser that carries no OpenSweep token; safety comes from the signed install
state below (same HMAC style as infrastructure/run_tokens).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets as pysecrets
import time

import redis.exceptions
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from api.dependencies import get_current_user, require_role
from config import settings
from domains.organizations.models import GitConnection
from domains.repositories.models import Repository
from domains.repositories.schemas import RepositoryDTO
from domains.repositories.services.registration import register_github_repo
from domains.repositories.services.repository_service import repository_to_dto
from domains.users.schemas import UserDTO
from domains.organizations.services.git_connections import (
    connection_summary,
    connection_token,
    list_pat_repos,
    maybe_create_repo_webhook,
    org_pat_connections,
)
from infrastructure import github_app as app_auth
from infrastructure.audit import write_audit
from infrastructure.github_app_store import get_github_app, secrets_dir
from logging_config import logger

router = APIRouter(prefix="/api/v1/github/app", tags=["github-app"])

_GITHUB_WEB = "https://github.com"

# The App install URL carries a signed state binding the flow to the caller's
# org; GitHub echoes it back to the setup URL together with installation_id,
# which is how an installation gets linked to ONE OpenSweep org. Generous
# window — picking repos on GitHub can take a while.
INSTALL_STATE_PREFIX = "kis_"
INSTALL_STATE_MAX_AGE_SECONDS = 3600


# ── Single-use nonce ledger ──────────────────────────────────────────────────
# The signed state alone is replayable within its expiry window (it travels
# in URLs → browser history / Referer / proxy logs). Minted states are recorded
# and consumed by the first successful /setup, so a captured state cannot
# link an attacker's installation to a victim org.
#
# Primary ledger: Redis (infrastructure/state_nonce_store.py) — shared across
# replicas. Fallback: the file ledger below (survives restarts, shared across
# workers via the secrets volume, NOT multi-replica safe). consume_state
# checks BOTH so states minted during a Redis outage still consume.
#
# Upgrade note: install states (kis_) were signature-only before this ledger
# existed — a pre-upgrade process never remembered them, so an install flow
# started before the deploy lands on /setup with an unknown state. /setup
# handles that by redirecting the user back to retry (a fresh /status mints a
# new state) instead of dead-ending in a 403.


def _pending_states_path():
    return secrets_dir() / "pending_app_states.json"


def _load_pending(now: int) -> dict[str, int]:
    try:
        raw = json.loads(_pending_states_path().read_text())
    except (OSError, ValueError):
        return {}
    # prune expired while loading
    return {
        s: int(ts)
        for s, ts in raw.items()
        if isinstance(ts, int | float) and 0 <= now - int(ts) <= INSTALL_STATE_MAX_AGE_SECONDS
    }


def _save_pending(pending: dict[str, int]) -> None:
    path = _pending_states_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pending))
    path.chmod(0o600)


def _file_remember_state(state: str, *, now: int | None = None) -> None:
    ts = int(now if now is not None else time.time())
    pending = _load_pending(ts)
    pending[state] = ts
    _save_pending(pending)


def _file_consume_state(state: str, *, now: int | None = None) -> bool:
    """True exactly once per minted state; removes it from the ledger."""
    ts = int(now if now is not None else time.time())
    pending = _load_pending(ts)
    if state not in pending:
        return False
    del pending[state]
    _save_pending(pending)
    return True


_warned_file_ledger_fallback = False


def _warn_file_ledger_fallback(exc: Exception) -> None:
    global _warned_file_ledger_fallback
    if not _warned_file_ledger_fallback:
        _warned_file_ledger_fallback = True
        logger.warning(
            "state nonce ledger: Redis unreachable — falling back to file ledger "
            f"(NOT multi-replica safe): {exc}",
            extra={"tag": "github"},
        )


async def remember_state(state: str, ttl_seconds: int = INSTALL_STATE_MAX_AGE_SECONDS) -> None:
    """Record a minted state in Redis; degrade to the file ledger when Redis
    is unreachable."""
    from infrastructure.state_nonce_store import remember_state_nonce

    try:
        await remember_state_nonce(state, ttl_seconds)
    except (redis.exceptions.RedisError, OSError) as exc:
        _warn_file_ledger_fallback(exc)
        _file_remember_state(state)


async def consume_state(state: str) -> bool:
    """True exactly once per minted state. Redis first; the file ledger is
    ALSO tried when Redis misses or errors — states minted by pre-upgrade
    processes (file only) and states minted during a Redis outage still
    consume."""
    from infrastructure.state_nonce_store import consume_state_nonce

    try:
        if await consume_state_nonce(state):
            return True
    except (redis.exceptions.RedisError, OSError) as exc:
        _warn_file_ledger_fallback(exc)
    return _file_consume_state(state)


# ── Signed install state (run_tokens-style HMAC, ts embedded) ───────────────
# Key precedence lives in infrastructure/state_signing.py (shared with the
# Slack install flow).


def _state_secret() -> str:
    from infrastructure.state_signing import state_secret

    return state_secret()


def _sign_install_state(ts: int, org_uid: str, nonce: str) -> str:
    digest = hmac.new(
        _state_secret().encode(), f"install.{ts}.{org_uid}.{nonce}".encode(), hashlib.sha256
    ).hexdigest()
    return digest[:40]


def mint_install_state(org_uid: str, *, now: int | None = None) -> str:
    """`kis_{ts}.{org_uid}.{nonce}.{sig}` — org uids never contain `.`."""
    ts = int(now if now is not None else time.time())
    nonce = pysecrets.token_hex(8)
    return f"{INSTALL_STATE_PREFIX}{ts}.{org_uid}.{nonce}.{_sign_install_state(ts, org_uid, nonce)}"


def verify_install_state(state: str, *, now: int | None = None) -> str:
    """The org uid the state was minted for, or "" when invalid/expired."""
    if not state or not state.startswith(INSTALL_STATE_PREFIX):
        return ""
    parts = state[len(INSTALL_STATE_PREFIX):].split(".")
    if len(parts) != 4:
        return ""
    raw_ts, org_uid, nonce, sig = parts
    try:
        ts = int(raw_ts)
    except ValueError:
        return ""
    current = int(now if now is not None else time.time())
    if not (0 <= current - ts <= INSTALL_STATE_MAX_AGE_SECONDS):
        return ""
    if not hmac.compare_digest(sig.encode(), _sign_install_state(ts, org_uid, nonce).encode()):
        return ""
    return org_uid


async def org_installation_ids(org_uid: str) -> set[int]:
    rows = await GitConnection.nodes.filter(org_uid=org_uid, provider="github")
    # kind="pat" rows carry a "pat:…" digest, not an installation id.
    return {
        int(link.external_id)
        for link in rows
        if (link.kind or "app") == "app" and str(link.external_id).isdigit()
    }


async def link_installation(
    installation_id: int, org_uid: str, *, account: str = "", linked_by: str = ""
) -> GitConnection:
    """Idempotent installation→org link; an existing link is never re-pointed
    (first org wins — relinking would silently hand one tenant's GitHub
    access to another)."""
    existing = await GitConnection.nodes.get_or_none(
        provider="github", external_id=str(installation_id)
    )
    if existing is not None:
        return existing
    return await GitConnection(
        provider="github",
        external_id=str(installation_id),
        org_uid=org_uid,
        display_name=account,
        linked_by=linked_by,
    ).save()


# ── DTOs ─────────────────────────────────────────────────────────────────────


class InstallationInfo(BaseModel):
    id: int
    account: str
    repos_count: int | None = None


class PatConnectionInfo(BaseModel):
    uid: str
    kind: str = "pat"
    account: str = ""
    created_at: str = ""


class AppStatusResponse(BaseModel):
    # connected = the caller's org can reach GitHub somehow: a configured
    # App and/or at least one org PAT connection. App fields are "" when no
    # App is configured (PAT-only instances).
    connected: bool
    slug: str = ""
    html_url: str = ""
    app_id: str = ""
    install_url: str = ""
    installations: list[InstallationInfo] = []
    installations_error: str = ""
    pat_connections: list[PatConnectionInfo] = []


class AvailableRepo(BaseModel):
    owner: str
    name: str
    full_name: str
    repo_id: int
    default_branch: str = ""
    private: bool = False
    description: str = ""
    registered: bool = False
    repository_uid: str = ""


class AvailableInstallation(BaseModel):
    """One repo group in the connect dialog — a GitHub App installation
    (id set) or an org PAT connection (connection_uid set, id=0)."""

    id: int = 0
    account: str = ""
    connection_uid: str = ""
    error: str = ""  # per-group fetch failure — never 500s the endpoint
    repos: list[AvailableRepo] = []


class AvailableReposResponse(BaseModel):
    connected: bool
    install_url: str = ""
    installations: list[AvailableInstallation] = []


class RegisterRepoRequest(BaseModel):
    # Exactly one of installation_id / connection_uid selects the credential
    # the repo is verified against and registered through.
    installation_id: int = 0
    connection_uid: str = ""
    owner: str
    name: str


# ── Pure helpers (unit-tested without DB/HTTP) ───────────────────────────────


async def _install_url(app, org_uid: str = "") -> str:
    """Install URL, org-bound: the state comes back to /setup with the
    installation id, linking the installation to the caller's org.

    The minted state is remembered for single-use consumption in /setup.
    Remembering is BEST-EFFORT: Redis down + file write failure must not
    break /status — the URL is still returned (its /setup will then 403,
    and the next /status mints a fresh, remembered state)."""
    if not app.slug:
        return ""
    url = f"{_GITHUB_WEB}/apps/{app.slug}/installations/new"
    if not org_uid:
        return url
    state = mint_install_state(org_uid)
    try:
        await remember_state(state, INSTALL_STATE_MAX_AGE_SECONDS)
    except Exception as exc:
        logger.warning(
            f"could not remember install state (URL still returned): {exc}",
            extra={"tag": "github"},
        )
    return f"{url}?state={state}"


def mark_registered(repos: list[dict], existing: list) -> list[dict]:
    """Cross-match raw GitHub repo dicts against Repository nodes/DTOs —
    match by github_repo_id first, then (owner, name) case-insensitive.
    Returns AvailableRepo-shaped dicts carrying registered/repository_uid."""
    by_id: dict[int, object] = {}
    by_full: dict[tuple[str, str], object] = {}
    for node in existing:
        raw_id = getattr(node, "github_repo_id", None)
        try:
            if raw_id is not None:
                by_id[int(raw_id)] = node
        except (TypeError, ValueError):
            pass
        owner = str(getattr(node, "github_owner", None) or "").lower()
        name = str(getattr(node, "github_repo", None) or "").lower()
        if owner and name:
            by_full.setdefault((owner, name), node)

    marked: list[dict] = []
    for gh in repos:
        owner = str((gh.get("owner") or {}).get("login") or "")
        name = str(gh.get("name") or "")
        node = None
        if gh.get("id") is not None:
            node = by_id.get(int(gh["id"]))
        if node is None:
            node = by_full.get((owner.lower(), name.lower()))
        marked.append(
            {
                "owner": owner,
                "name": name,
                "full_name": str(gh.get("full_name") or (f"{owner}/{name}" if owner else name)),
                "repo_id": int(gh.get("id") or 0),
                "default_branch": str(gh.get("default_branch") or ""),
                "private": bool(gh.get("private")),
                "description": str(gh.get("description") or ""),
                "registered": node is not None,
                "repository_uid": str(getattr(node, "uid", "") or "") if node is not None else "",
            }
        )
    return marked


def find_installation_repo(repos: list[dict], *, owner: str, name: str) -> dict | None:
    """Membership check for register-repo: the (owner, name) the client asked
    for must actually be in the installation's live repo list — matched
    case-insensitively. None when absent."""
    want = ((owner or "").strip().lower(), (name or "").strip().lower())
    if not want[0] or not want[1]:
        return None
    for gh in repos:
        gh_owner = str((gh.get("owner") or {}).get("login") or "").lower()
        gh_name = str(gh.get("name") or "").lower()
        if (gh_owner, gh_name) == want:
            return gh
    return None


# ── Routes ───────────────────────────────────────────────────────────────────


@router.get("/status", response_model=AppStatusResponse, operation_id="opensweep_github_app_status")
async def app_status(user: UserDTO = Depends(get_current_user)) -> AppStatusResponse:
    """Connection status: the App + live installations (tolerates GitHub
    failures) and the org's PAT connections."""
    app = get_github_app()
    pat_connections = [
        PatConnectionInfo(**connection_summary(c))
        for c in await org_pat_connections(user.org_uid)
    ]
    if app is None:
        return AppStatusResponse(connected=bool(pat_connections), pat_connections=pat_connections)

    # Tenancy: callers see only installations linked to their org; the
    # platform admin sees everything (including not-yet-linked ones).
    linked = await org_installation_ids(user.org_uid)
    installations: list[InstallationInfo] = []
    installations_error = ""
    try:
        for inst in await app_auth.list_installations():
            inst_id = int(inst.get("id") or 0)
            if not inst_id:
                continue
            if not user.is_platform_admin and inst_id not in linked:
                continue
            installations.append(
                InstallationInfo(
                    id=inst_id,
                    account=str((inst.get("account") or {}).get("login") or ""),
                    repos_count=await app_auth.count_installation_repos(inst_id),
                )
            )
    except Exception as exc:
        # Live GitHub reads must never break the status card.
        installations_error = str(exc)[:200]
        logger.warning(f"GitHub App installations fetch failed: {exc}", extra={"tag": "github"})

    return AppStatusResponse(
        connected=True,
        slug=app.slug,
        html_url=app.html_url,
        app_id=app.app_id,
        install_url=await _install_url(app, user.org_uid),
        installations=installations,
        installations_error=installations_error,
        pat_connections=pat_connections,
    )


@router.get(
    "/available-repos",
    response_model=AvailableReposResponse,
    operation_id="opensweep_github_available_repos",
)
async def available_repos(
    user: UserDTO = Depends(get_current_user),
) -> AvailableReposResponse:
    """Every repo reachable through the App's installations AND the org's
    PAT connections, cross-matched against registered Repository nodes.
    Per-group GitHub failures land in that group's `error` — this endpoint
    never 500s on them."""
    app = get_github_app()
    pat_conns = await org_pat_connections(user.org_uid)
    if app is None and not pat_conns:
        return AvailableReposResponse(connected=False)

    # Registered-markers come from the caller's org only — repos registered by
    # OTHER orgs show as unregistered here, and register-repo accepts them
    # (each org gets its own Repository node for the same GitHub repo).
    existing = await Repository.nodes.filter(org_uid=user.org_uid)
    installations: list[AvailableInstallation] = []

    if app is not None:
        linked = await org_installation_ids(user.org_uid)
        try:
            raw_installations = await app_auth.list_installations()
        except Exception as exc:
            logger.warning(
                f"GitHub App installations fetch failed: {exc}", extra={"tag": "github"}
            )
            raw_installations = []
        for inst in raw_installations:
            inst_id = int(inst.get("id") or 0)
            if not inst_id:
                continue
            if not user.is_platform_admin and inst_id not in linked:
                continue
            error = ""
            repos: list[AvailableRepo] = []
            try:
                raw_repos = await app_auth.list_installation_repositories(inst_id)
                repos = [AvailableRepo(**item) for item in mark_registered(raw_repos, existing)]
            except Exception as exc:
                error = str(exc)[:200]
                logger.warning(
                    f"repo list for installation {inst_id} failed: {exc}", extra={"tag": "github"}
                )
            installations.append(
                AvailableInstallation(
                    id=inst_id,
                    account=str((inst.get("account") or {}).get("login") or ""),
                    error=error,
                    repos=repos,
                )
            )

    # Org PAT connections — same group shape, keyed by connection_uid.
    for conn in pat_conns:
        error = ""
        repos = []
        token = connection_token(conn)
        if not token:
            error = "token cannot be decrypted (OPENSWEEP_SECRETS_KEY changed?)"
        else:
            try:
                raw_repos = await list_pat_repos(token)
                repos = [AvailableRepo(**item) for item in mark_registered(raw_repos, existing)]
            except Exception as exc:
                error = str(exc)[:200]
                logger.warning(
                    f"repo list for connection {conn.uid} failed: {exc}", extra={"tag": "github"}
                )
        installations.append(
            AvailableInstallation(
                connection_uid=conn.uid,
                account=conn.display_name or "token",
                error=error,
                repos=repos,
            )
        )

    return AvailableReposResponse(
        connected=True,
        install_url=await _install_url(app, user.org_uid) if app is not None else "",
        installations=installations,
    )


@router.post(
    "/register-repo",
    response_model=RepositoryDTO,
    status_code=201,
    operation_id="opensweep_github_register_repo",
)
async def register_repo(
    req: RegisterRepoRequest,
    user: UserDTO = Depends(require_role("maintainer")),
) -> RepositoryDTO:
    """Register ONE selected repo. Only the identifiers come from the client —
    the repo must be live-verified against the credential's repo list
    (installation or PAT connection), and default_branch/repo_id are taken
    from GitHub, never the request body."""
    pat_conn = None
    pat_token = ""
    if req.connection_uid:
        # PAT-connection path: the connection must belong to the caller's org.
        pat_conn = await GitConnection.nodes.get_or_none(uid=req.connection_uid, kind="pat")
        if pat_conn is None or pat_conn.org_uid != user.org_uid:
            raise HTTPException(status_code=404, detail="not found")
        pat_token = connection_token(pat_conn)
        if not pat_token:
            raise HTTPException(
                status_code=409,
                detail="connection token cannot be decrypted — re-add the token",
            )
        try:
            raw_repos = await list_pat_repos(pat_token)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"could not list repositories for this token: {str(exc)[:200]}",
            ) from exc
        link = None
    else:
        if not req.installation_id:
            raise HTTPException(
                status_code=422, detail="installation_id or connection_uid is required"
            )
        app = get_github_app()
        if app is None:
            raise HTTPException(status_code=409, detail="no GitHub App connected")

        # Tenancy: the installation must belong to the caller's org. Platform
        # admins may register through a not-yet-linked installation — doing so
        # claims it for their org.
        link = await GitConnection.nodes.get_or_none(
            provider="github", external_id=str(req.installation_id)
        )
        if link is None:
            if not user.is_platform_admin:
                raise HTTPException(status_code=404, detail="not found")
        elif link.org_uid != user.org_uid:
            raise HTTPException(status_code=404, detail="not found")

        try:
            raw_repos = await app_auth.list_installation_repositories(req.installation_id)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"could not list repositories for installation {req.installation_id}: "
                f"{str(exc)[:200]}",
            ) from exc

    gh = find_installation_repo(raw_repos, owner=req.owner, name=req.name)
    if gh is None:
        raise HTTPException(
            status_code=404,
            detail=f"{req.owner}/{req.name} is not available through this connection",
        )

    # Same-org conflict check — the same GitHub repo may be registered by
    # multiple orgs (each gets its own Repository node); only a duplicate
    # within the caller's org is a conflict.
    existing = await Repository.nodes.filter(org_uid=user.org_uid)
    marked = mark_registered([gh], existing)[0]
    if marked["registered"]:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{marked['full_name']} is already registered "
                f"(repository_uid={marked['repository_uid']})"
            ),
        )

    node = await register_github_repo(
        org_uid=user.org_uid,
        owner=marked["owner"],
        name=marked["name"],
        repo_id=marked["repo_id"] or None,
        default_branch=marked["default_branch"],
        installation_id=req.installation_id or None,
        connection_uid=pat_conn.uid if pat_conn is not None else None,
        description=marked["description"],
    )
    if pat_conn is not None:
        # What the App's built-in webhook gives installation repos — created
        # with the connection's token when the instance is publicly reachable.
        await maybe_create_repo_webhook(
            token=pat_token, owner=marked["owner"], name=marked["name"]
        )
    elif link is None:
        await link_installation(
            req.installation_id, user.org_uid, linked_by=user.uid
        )
    return repository_to_dto(node)


@router.get("/setup", operation_id="opensweep_github_app_setup")
async def installation_setup(
    installation_id: int = 0, setup_action: str = "", state: str = ""
) -> RedirectResponse:
    """GitHub redirects the installer's browser here after they install the
    App (manifest setup_url). Exempt from TokenAuthMiddleware — trust is the
    signed install state, which carries the org the flow was started from.
    Links the installation to that org (first org wins; never re-pointed)."""
    org_uid = verify_install_state(state)
    base = (settings.OPENSWEEP_FRONTEND_BASE_URL or "").rstrip("/")
    if not org_uid:
        raise HTTPException(status_code=403, detail="invalid or expired state")
    # Single-use: a captured install state cannot be replayed to link a second
    # installation. Safe to consume here — every /status (and /available-repos)
    # call mints a FRESH install state, so a user who retries the install flow
    # always gets a new, unconsumed one. A consume miss is NOT necessarily an
    # attack: states minted pre-upgrade (never ledgered) or a double-click on
    # the GitHub redirect land here too — send the browser back to retry
    # instead of dead-ending an operator flow in raw JSON.
    if not await consume_state(state):
        logger.warning(
            "install state not consumable (replayed, pre-upgrade, or unknown); "
            "redirecting user to retry",
            extra={"tag": "github"},
        )
        return RedirectResponse(
            url=f"{base}/repositories?connect=1&install_error=state_reused",
            status_code=302,
        )
    if installation_id:
        link = await link_installation(installation_id, org_uid)
        if link.org_uid == org_uid:
            await write_audit(
                kind="github_app.installation_linked",
                subject_uid=str(installation_id),
                subject_type="GitConnection",
                actor_uid=org_uid,
                payload={"org_uid": org_uid, "setup_action": setup_action},
            )
        else:
            logger.warning(
                f"installation {installation_id} already linked to org {link.org_uid}; "
                f"ignoring setup for org {org_uid}",
                extra={"tag": "github"},
            )
    return RedirectResponse(url=f"{base}/repositories?connect=1", status_code=302)
