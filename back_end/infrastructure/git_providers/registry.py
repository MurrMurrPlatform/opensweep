"""Provider registry — dispatches a Repository to its git provider.

A `GitProvider` bundles the two credential-aware entry points every call
site needs: an API client for the repo, and the raw git credential (clone /
push auth). Providers self-register at import time (see github.py); lookup
is by `Repository.provider` (default "github" — pre-provider nodes carry no
value)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from infrastructure.git_providers.protocol import GitProviderClient


@dataclass(frozen=True)
class GitProvider:
    key: str
    client_for_repo: Callable[[Any], GitProviderClient]
    git_credentials: Callable[[Any], Awaitable[str]]


_REGISTRY: dict[str, GitProvider] = {}


def register_provider(provider: GitProvider) -> None:
    _REGISTRY[provider.key] = provider


def repo_provider(repo: Any) -> str:
    """The provider key for a Repository node/DTO — absent/empty ⇒ github."""
    return str(getattr(repo, "provider", "") or "github")


def _provider_for(repo: Any) -> GitProvider:
    key = repo_provider(repo)
    provider = _REGISTRY.get(key)
    if provider is None:
        raise RuntimeError(f"unknown git provider {key!r}")
    return provider


def get_provider_client(repo: Any) -> GitProviderClient:
    """API client bound to this repo's credential (provider-dispatched)."""
    return _provider_for(repo).client_for_repo(repo)


async def get_git_credentials(repo: Any) -> str:
    """The git/API credential for one repo (provider-dispatched). Empty
    string when nothing is configured — callers decide how to surface it."""
    return await _provider_for(repo).git_credentials(repo)
