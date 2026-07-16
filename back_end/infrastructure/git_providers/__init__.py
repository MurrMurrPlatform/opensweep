"""Git-provider abstraction.

Call sites depend on this package instead of naming GitHub directly:

    from infrastructure.git_providers import get_provider_client, get_git_credentials

GitHub is the only registered provider today — importing this package
registers it (github.py side effect). A second provider adds one module +
one register_provider() call; no call-site changes."""

from infrastructure.git_providers import github as _github  # noqa: F401  (registers "github")
from infrastructure.git_providers.protocol import GitProviderClient
from infrastructure.git_providers.registry import (
    get_git_credentials,
    get_provider_client,
    register_provider,
    repo_provider,
)

__all__ = [
    "GitProviderClient",
    "get_git_credentials",
    "get_provider_client",
    "register_provider",
    "repo_provider",
]
