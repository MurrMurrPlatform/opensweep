"""Git-provider abstraction (infrastructure/git_providers) — offline tests.

The abstraction is a pure refactor: GitHub stays the only implementation.
Covers: provider-dispatched client selection (parity with
github_app.get_client_for_repo), credential passthrough to
get_repo_git_token, the provider-key default/unknown-key behavior, runtime
structural conformance of GitHubClient, and the m0004 migration's shape.
"""

import asyncio
from types import SimpleNamespace

import pytest

from config import settings
from infrastructure import github_app, github_app_store, redis_client
from infrastructure.git_providers import (
    GitProviderClient,
    get_git_credentials,
    get_provider_client,
    repo_provider,
)
from infrastructure.github_client import GitHubClient


@pytest.fixture(autouse=True)
def isolated_app_store(monkeypatch, tmp_path):
    """Every test starts with no App configured and empty caches."""
    from tests.fake_redis import FakeAsyncRedis

    monkeypatch.setattr(settings, "ARTIFACT_STORE_ROOT", str(tmp_path / "var" / "artifacts"))
    monkeypatch.setattr(settings, "GITHUB_APP_ID", "")
    monkeypatch.setattr(settings, "GITHUB_APP_SLUG", "")
    monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY", "")
    monkeypatch.setattr(settings, "GITHUB_PRIVATE_KEY_PATH", "")
    fake_redis = FakeAsyncRedis()
    monkeypatch.setattr(redis_client, "get_async_redis", lambda: fake_redis)
    github_app_store._invalidate_cache()
    asyncio.run(github_app.clear_token_cache())
    yield
    github_app_store._invalidate_cache()
    asyncio.run(github_app.clear_token_cache())


def _repo(installation_id=None, **extra):
    return SimpleNamespace(github_installation_id=installation_id, **extra)


# ── get_provider_client: same selection behavior as get_client_for_repo ─────


def test_get_provider_client_selects_installation_token_client(monkeypatch):
    monkeypatch.setattr(
        github_app, "get_github_app",
        lambda: github_app_store.GitHubAppConfig(app_id="1", pem="x"),
    )
    client = get_provider_client(_repo(55))
    assert client._token_source is not None
    assert client._token_source.installation_id == 55
    assert client.is_active  # active without any PAT

    # Parity with the wrapped implementation.
    direct = github_app.get_client_for_repo(_repo(55))
    assert direct._token_source.installation_id == client._token_source.installation_id


def test_get_provider_client_falls_back_to_pat_client(monkeypatch):
    monkeypatch.setattr(
        github_app, "get_github_app",
        lambda: github_app_store.GitHubAppConfig(app_id="1", pem="x"),
    )
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_pat")
    assert get_provider_client(_repo(None))._token_source is None

    # No App connected → PAT/default client even with an installation id.
    monkeypatch.setattr(github_app, "get_github_app", lambda: None)
    assert get_provider_client(_repo(55))._token_source is None


# ── get_git_credentials: passthrough to get_repo_git_token ──────────────────


async def test_get_git_credentials_delegates_to_get_repo_git_token(monkeypatch):
    seen: list = []

    async def fake_token(repo):
        seen.append(repo)
        return "tok-xyz"

    monkeypatch.setattr(github_app, "get_repo_git_token", fake_token)
    repo = _repo(55)
    assert await get_git_credentials(repo) == "tok-xyz"
    assert seen == [repo]


# ── repo_provider + unknown-provider dispatch ────────────────────────────────


def test_repo_provider_defaults_to_github():
    assert repo_provider(SimpleNamespace()) == "github"  # attribute missing
    assert repo_provider(SimpleNamespace(provider="")) == "github"
    assert repo_provider(SimpleNamespace(provider=None)) == "github"
    assert repo_provider(SimpleNamespace(provider="gitlab")) == "gitlab"


def test_unknown_provider_key_raises():
    with pytest.raises(RuntimeError, match="unknown git provider 'gitlab'"):
        get_provider_client(SimpleNamespace(provider="gitlab"))


# ── Structural conformance ───────────────────────────────────────────────────


def test_github_client_satisfies_protocol():
    assert isinstance(GitHubClient(token="x"), GitProviderClient)


# ── m0004 migration sanity ───────────────────────────────────────────────────


def test_m0004_loads_and_is_reversible():
    import migrations.m0004_git_connection as m0004
    from infrastructure.migration_runner import load_definitions
    from migrations import migration_modules

    assert m0004.VERSION == 4
    defs = load_definitions(migration_modules())  # contiguity check included
    d = next(d for d in defs if d.version == 4)
    assert d.name == "git-connection"
    assert d.reversible
    # Relabels + backfills must both be undoable via stored statements.
    assert any("GitConnection" in stmt for stmt in d.up)
    assert any("GithubInstallation" in stmt for stmt in d.down)
    assert any("r.provider" in stmt for stmt in d.up)
    assert any("REMOVE r.provider" in stmt for stmt in d.down)
