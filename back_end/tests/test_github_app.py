"""GitHub App env configuration + installation flow (§7) — offline unit tests.

The App is deployment config now (scripts/github-app-setup.sh): created
outside the platform, read from GITHUB_APP_* env vars. Covers: the env
loader (inline/base64/path private key, html_url derivation), App JWT claims,
installation-token caching (mocked HTTP), installation-webhook dispositions
(pure), slug dedup, credential selection (App vs PAT), webhook-secret
resolution, and the TokenAuthMiddleware wiring (setup exempt; creation
endpoints gone).
"""

import asyncio
import base64
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

import api.v1.github_app as app_module
from api.v1.github_app import (
    INSTALL_STATE_MAX_AGE_SECONDS,
    mint_install_state,
)
from api.v1.github_webhooks import installation_disposition
from app import app as real_app
from config import settings
from domains.repositories.services.registration import dedupe_slug, slug_for_repo_name
from infrastructure import github_app, github_app_store, redis_client
from tests.fake_redis import FakeAsyncRedis


@pytest.fixture(autouse=True)
def isolated_app_store(monkeypatch, tmp_path):
    """Every test starts with no App configured, empty caches, a tmp secrets
    dir (file ledger), and an isolated in-memory fake Redis (yielded for
    tests that inspect it)."""
    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(tmp_path / "var" / "artifacts"))
    monkeypatch.setattr(settings, "GITHUB_APP_ID", "")
    monkeypatch.setattr(settings, "GITHUB_APP_SLUG", "")
    monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY", "")
    monkeypatch.setattr(settings, "GITHUB_PRIVATE_KEY_PATH", "")
    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", "")
    fake_redis = FakeAsyncRedis()
    monkeypatch.setattr(redis_client, "get_async_redis", lambda: fake_redis)

    async def _no_pat_connections(org_uid):
        return []

    # Offline tests: the endpoints' PAT-connection reads never hit the graph.
    monkeypatch.setattr(app_module, "org_pat_connections", _no_pat_connections)
    github_app_store._invalidate_cache()
    asyncio.run(github_app.clear_token_cache())
    yield fake_redis
    github_app_store._invalidate_cache()
    asyncio.run(github_app.clear_token_cache())


TEST_PEM = "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n"


def configure_github_app(
    monkeypatch,
    *,
    app_id: str = "4242",
    slug: str = "opensweep-ab12cd34",
    pem: str = TEST_PEM,
    webhook_secret: str = "whsec-123",
) -> None:
    """Point settings at a configured App — env is the only source."""
    monkeypatch.setattr(settings, "GITHUB_APP_ID", app_id)
    monkeypatch.setattr(settings, "GITHUB_APP_SLUG", slug)
    monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY", pem)
    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", webhook_secret)
    github_app_store._invalidate_cache()


def _rsa_keypair() -> tuple[str, str]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return pem, pub


# ── Env configuration loader ─────────────────────────────────────────────────


def test_no_env_means_no_app():
    assert github_app_store.get_github_app() is None


def test_env_config_full(monkeypatch):
    configure_github_app(monkeypatch)
    app = github_app_store.get_github_app()
    assert app is not None
    assert app.app_id == "4242"
    assert app.slug == "opensweep-ab12cd34"
    assert app.pem == TEST_PEM
    assert app.webhook_secret == "whsec-123"
    # html_url is derived from the slug — no separate env var.
    assert app.html_url == "https://github.com/apps/opensweep-ab12cd34"


def test_env_config_accepts_base64_pem(monkeypatch):
    """The setup script writes base64 (survives env transport unmangled)."""
    configure_github_app(monkeypatch, pem=base64.b64encode(TEST_PEM.encode()).decode())
    app = github_app_store.get_github_app()
    assert app is not None and app.pem == TEST_PEM


def test_env_config_key_path(monkeypatch, tmp_path):
    key_file = tmp_path / "app.pem"
    key_file.write_text(TEST_PEM)
    configure_github_app(monkeypatch, pem="")
    monkeypatch.setattr(settings, "GITHUB_PRIVATE_KEY_PATH", str(key_file))
    github_app_store._invalidate_cache()
    app = github_app_store.get_github_app()
    assert app is not None and app.pem == TEST_PEM


def test_env_config_inline_key_wins_over_path(monkeypatch, tmp_path):
    key_file = tmp_path / "app.pem"
    key_file.write_text("-----BEGIN PRIVATE KEY-----\nfrom-file\n-----END PRIVATE KEY-----\n")
    configure_github_app(monkeypatch)
    monkeypatch.setattr(settings, "GITHUB_PRIVATE_KEY_PATH", str(key_file))
    github_app_store._invalidate_cache()
    assert github_app_store.get_github_app().pem == TEST_PEM


def test_env_config_requires_app_id_and_key(monkeypatch):
    configure_github_app(monkeypatch, app_id="")  # key without id
    assert github_app_store.get_github_app() is None
    configure_github_app(monkeypatch, pem="")  # id without key
    assert github_app_store.get_github_app() is None


def test_env_config_rejects_non_pem_key(monkeypatch):
    configure_github_app(monkeypatch, pem="definitely-not-a-pem")
    assert github_app_store.get_github_app() is None
    # base64 of non-PEM junk is refused too.
    configure_github_app(monkeypatch, pem=base64.b64encode(b"junk").decode())
    assert github_app_store.get_github_app() is None


def test_env_config_unreadable_key_path_means_no_app(monkeypatch, tmp_path):
    configure_github_app(monkeypatch, pem="")
    monkeypatch.setattr(settings, "GITHUB_PRIVATE_KEY_PATH", str(tmp_path / "missing.pem"))
    github_app_store._invalidate_cache()
    assert github_app_store.get_github_app() is None


def test_env_config_without_slug_has_no_urls(monkeypatch):
    """slug is optional (older manual Apps) — App auth works, install URLs
    are just unavailable."""
    configure_github_app(monkeypatch, slug="")
    app = github_app_store.get_github_app()
    assert app is not None
    assert app.html_url == ""


def test_env_config_cache_invalidated_by_env_change(monkeypatch):
    configure_github_app(monkeypatch)
    assert github_app_store.get_github_app().slug == "opensweep-ab12cd34"
    # No explicit invalidation: the fingerprint change is enough.
    monkeypatch.setattr(settings, "GITHUB_APP_SLUG", "opensweep-renamed")
    assert github_app_store.get_github_app().slug == "opensweep-renamed"


# ── App JWT ──────────────────────────────────────────────────────────────────


def test_make_app_jwt_claims():
    pem, pub = _rsa_keypair()
    now = 1_700_000_000
    token = github_app.make_app_jwt("4242", pem, now=now)
    claims = pyjwt.decode(token, pub, algorithms=["RS256"], options={"verify_exp": False})
    assert claims == {"iat": now - 60, "exp": now + 540, "iss": "4242"}


# ── Installation token cache ─────────────────────────────────────────────────


async def test_installation_token_cached_until_refresh_margin(monkeypatch):
    minted: list[int] = []

    async def fake_request(app, installation_id):
        minted.append(installation_id)
        return {
            "token": f"ghs_tok{len(minted)}",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }

    monkeypatch.setattr(github_app, "_request_installation_token", fake_request)
    monkeypatch.setattr(
        github_app, "get_github_app",
        lambda: github_app_store.GitHubAppConfig(app_id="1", pem="x"),
    )

    t1 = await github_app.get_installation_token(77)
    t2 = await github_app.get_installation_token(77)
    assert t1 == t2 == "ghs_tok1"
    assert minted == [77]

    # A different installation mints its own token.
    t3 = await github_app.get_installation_token(88)
    assert t3 == "ghs_tok2"
    assert minted == [77, 88]

    # Within 5 min of expiry → re-mint (both cache levels near expiry — the
    # Redis L2 entry is written alongside L1, so age them together).
    near_expiry = github_app._CachedToken(
        token="ghs_tok1", expires_at=datetime.now(UTC) + timedelta(minutes=4)
    )
    github_app._token_cache[77] = near_expiry
    await github_app._redis_write_token(77, near_expiry)
    t4 = await github_app.get_installation_token(77)
    assert t4 == "ghs_tok3"
    assert minted == [77, 88, 77]


async def test_installation_token_requires_connected_app(monkeypatch):
    monkeypatch.setattr(github_app, "get_github_app", lambda: None)
    with pytest.raises(RuntimeError, match="no GitHub App connected"):
        await github_app.get_installation_token(1)


# ── Installation webhook dispositions (pure) ─────────────────────────────────


def test_installation_created_connects_payload_repos():
    d = installation_disposition(
        event="installation",
        action="created",
        payload={
            "installation": {"id": 55},
            "repositories": [{"id": 1, "full_name": "acme/api", "name": "api"}],
        },
    )
    assert d.installation_id == 55
    assert [r["full_name"] for r in d.connect] == ["acme/api"]
    assert d.disconnect == [] and d.disconnect_all is False


def test_installation_deleted_disconnects_all():
    d = installation_disposition(
        event="installation", action="deleted", payload={"installation": {"id": 55}}
    )
    assert d.disconnect_all is True
    assert d.connect == [] and d.disconnect == []


def test_installation_other_actions_are_noops():
    for action in ("suspend", "unsuspend", "new_permissions_accepted"):
        assert (
            installation_disposition(
                event="installation", action=action, payload={"installation": {"id": 55}}
            )
            is None
        )


def test_installation_repositories_added_and_removed():
    d = installation_disposition(
        event="installation_repositories",
        action="added",
        payload={
            "installation": {"id": 55},
            "repositories_added": [{"id": 2, "full_name": "acme/web", "name": "web"}],
            "repositories_removed": [{"id": 3, "full_name": "acme/old", "name": "old"}],
        },
    )
    assert [r["name"] for r in d.connect] == ["web"]
    assert [r["name"] for r in d.disconnect] == ["old"]
    assert d.disconnect_all is False


def test_installation_event_without_id_is_noop():
    assert installation_disposition(event="installation", action="created", payload={}) is None


def test_slug_generation_and_dedup():
    assert slug_for_repo_name("My.Repo_Name") == "my-repo-name"
    assert slug_for_repo_name("---") == "repo"
    assert dedupe_slug("api", set()) == "api"
    assert dedupe_slug("api", {"api"}) == "api-2"
    assert dedupe_slug("api", {"api", "api-2", "api-3"}) == "api-4"


# ── Credential selection: App vs PAT ─────────────────────────────────────────


def _repo(installation_id=None):
    return SimpleNamespace(github_installation_id=installation_id)


def test_uses_app_auth_selection_rule():
    assert github_app.uses_app_auth(_repo(55), app_connected=True) is True
    assert github_app.uses_app_auth(_repo(None), app_connected=True) is False
    assert github_app.uses_app_auth(_repo(55), app_connected=False) is False
    assert github_app.uses_app_auth(_repo(0), app_connected=True) is False
    assert github_app.uses_app_auth(_repo("nonsense"), app_connected=True) is False


async def test_get_repo_git_token_prefers_installation_token(monkeypatch):
    monkeypatch.setattr(
        github_app, "get_github_app",
        lambda: github_app_store.GitHubAppConfig(app_id="1", pem="x"),
    )

    async def fake_token(installation_id):
        return f"ghs_for_{installation_id}"

    monkeypatch.setattr(github_app, "get_installation_token", fake_token)
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_pat")

    assert await github_app.get_repo_git_token(_repo(55)) == "ghs_for_55"
    assert await github_app.get_repo_git_token(_repo(None)) == "ghp_pat"


async def test_get_repo_git_token_pat_when_no_app(monkeypatch):
    monkeypatch.setattr(github_app, "get_github_app", lambda: None)
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_pat")
    assert await github_app.get_repo_git_token(_repo(55)) == "ghp_pat"


async def test_get_repo_git_token_falls_back_to_pat_on_mint_failure(monkeypatch):
    monkeypatch.setattr(
        github_app, "get_github_app",
        lambda: github_app_store.GitHubAppConfig(app_id="1", pem="x"),
    )

    async def boom(installation_id):
        raise RuntimeError("github is down")

    monkeypatch.setattr(github_app, "get_installation_token", boom)
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_pat")
    assert await github_app.get_repo_git_token(_repo(55)) == "ghp_pat"

    monkeypatch.setattr(settings, "GITHUB_TOKEN", "")
    with pytest.raises(RuntimeError, match="github is down"):
        await github_app.get_repo_git_token(_repo(55))


def test_get_client_for_repo_selects_token_source(monkeypatch):
    monkeypatch.setattr(
        github_app, "get_github_app",
        lambda: github_app_store.GitHubAppConfig(app_id="1", pem="x"),
    )
    client = github_app.get_client_for_repo(_repo(55))
    assert client._token_source is not None
    assert client._token_source.installation_id == 55
    assert client.is_active  # active without any PAT

    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_pat")
    pat_client = github_app.get_client_for_repo(_repo(None))
    assert pat_client._token_source is None

    monkeypatch.setattr(github_app, "get_github_app", lambda: None)
    assert github_app.get_client_for_repo(_repo(55))._token_source is None


# ── Webhook secret resolution ────────────────────────────────────────────────


def test_webhook_secrets_env_and_dedup(monkeypatch):
    from api.v1.github_webhooks import _webhook_secrets

    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", "env-secret")
    github_app_store._invalidate_cache()
    assert _webhook_secrets() == ["env-secret"]

    # A configured App shares GITHUB_WEBHOOK_SECRET — no duplicate entry.
    configure_github_app(monkeypatch, webhook_secret="env-secret")
    assert _webhook_secrets() == ["env-secret"]

    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", "")
    github_app_store._invalidate_cache()
    assert _webhook_secrets() == []


# ── Middleware wiring + removed creation endpoints ───────────────────────────


def test_setup_exempt_from_token_auth(monkeypatch):
    """With auth ON and no token presented, /setup must reach the handler
    (403 invalid state), NOT the middleware's 401."""
    monkeypatch.setattr(settings, "OPENSWEEP_AUTH_TOKEN", "sekrit")
    res = TestClient(real_app).get("/api/v1/github/app/setup?state=bogus")
    assert res.status_code == 403
    assert res.json()["detail"] == "invalid or expired state"


def test_status_gated_by_token_auth(monkeypatch):
    monkeypatch.setattr(settings, "OPENSWEEP_AUTH_TOKEN", "sekrit")
    assert TestClient(real_app).get("/api/v1/github/app/status").status_code == 401


def test_creation_endpoints_are_gone():
    """App creation moved to scripts/github-app-setup.sh — the manifest,
    callback and disconnect endpoints must not exist (nor be auth-exempt)."""
    client = TestClient(real_app)
    assert client.post("/api/v1/github/app/manifest", json={}).status_code == 404
    assert client.get("/api/v1/github/app/callback?code=c&state=s").status_code == 404
    assert client.post("/api/v1/github/app/disconnect").status_code == 404


def test_status_disconnected_shape():
    res = TestClient(real_app).get("/api/v1/github/app/status")
    assert res.status_code == 200
    body = res.json()
    assert body["connected"] is False
    assert body["installations"] == []


# ── Install-state nonce ledger (single-use) ──────────────────────────────────


def test_state_nonce_is_single_use_and_unknown_states_are_refused():
    import api.v1.github_app as module

    state = mint_install_state("org-1")
    # never remembered → cannot be consumed
    assert asyncio.run(module.consume_state(state)) is False
    asyncio.run(module.remember_state(state))
    assert asyncio.run(module.consume_state(state)) is True
    assert asyncio.run(module.consume_state(state)) is False  # consumed exactly once
    # file ledger: entries older than the install-state window are pruned
    long_ago = int(time.time()) - INSTALL_STATE_MAX_AGE_SECONDS - 60
    old_state = mint_install_state("org-1", now=long_ago)
    module._file_remember_state(old_state, now=long_ago)
    assert module._file_consume_state(old_state) is False
    # a still-valid entry survives pruning
    recent = mint_install_state("org-2", now=int(time.time()) - 1800)
    module._file_remember_state(recent, now=int(time.time()) - 1800)
    assert module._file_consume_state(recent) is True
