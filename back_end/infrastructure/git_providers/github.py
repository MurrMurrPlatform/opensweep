"""GitHub provider — thin adapter over infrastructure/github_app.

The real implementation (installation-token vs PAT selection, token minting,
caching) lives in `infrastructure.github_app.get_client_for_repo` /
`get_repo_git_token` and stays there unchanged; this module only registers
it under the "github" key. Imports are lazy so monkeypatching the
github_app module in tests keeps working."""

from __future__ import annotations

from typing import Any

from infrastructure.git_providers.protocol import GitProviderClient
from infrastructure.git_providers.registry import GitProvider, register_provider


def _client_for_repo(repo: Any) -> GitProviderClient:
    from infrastructure.github_app import get_client_for_repo

    return get_client_for_repo(repo)


async def _git_credentials(repo: Any) -> str:
    from infrastructure.github_app import get_repo_git_token

    return await get_repo_git_token(repo)


GITHUB_PROVIDER = GitProvider(
    key="github",
    client_for_repo=_client_for_repo,
    git_credentials=_git_credentials,
)

register_provider(GITHUB_PROVIDER)
