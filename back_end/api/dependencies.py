"""Shared FastAPI dependencies.

`get_current_user` resolves the authenticated user:
  - Zitadel OIDC: TokenAuthMiddleware verified the JWT and stashed claims in
    scope["state"] — resolve/upsert the User node from them.
  - Otherwise (auth disabled, shared token, or run token): the hardcoded
    local user, unchanged v1 behavior.

Service singletons live here as plain lru_cache factories — the services are
stateless (or carry only a lazily-built client), so one instance per process
is all the "container" this app ever needed.
"""

from collections.abc import Callable
from functools import lru_cache

from fastapi import Depends, HTTPException
from starlette.requests import HTTPConnection

from domains.execution.services.sandbox_service import SandboxService
from domains.llm_providers.services.llm_provider_service import LLMProviderService
from domains.metrics.services.metrics_service import MetricsService
from domains.repositories.services.github_service import GitHubService
from domains.repositories.services.repository_service import RepositoryService
from domains.users.schemas import UserDTO, role_at_least
from domains.users.services.local_user import get_local_user


async def get_current_user(connection: HTTPConnection) -> UserDTO:
    # HTTPConnection (not Request) so WebSocket routes can inject this too.
    state = connection.scope.get("state") or {}
    claims = state.get("oidc_claims")
    if claims:
        from domains.users.services.oidc_user import resolve_oidc_user

        return await resolve_oidc_user(claims, state.get("oidc_access_token", ""))
    return get_local_user()


def require_role(minimum: str) -> Callable[..., UserDTO]:
    """Dependency factory: the current user must hold at least `minimum` role
    (viewer < maintainer < admin). 403 otherwise."""

    def _dependency(user: UserDTO = Depends(get_current_user)) -> UserDTO:
        if not role_at_least(user.role, minimum):
            raise HTTPException(
                status_code=403,
                detail=f"requires role '{minimum}' or higher (you are '{user.role}')",
            )
        return user

    return _dependency


def require_org_owner(user: UserDTO = Depends(get_current_user)) -> UserDTO:
    """Org management (rename, members, invitations) is owner-only."""
    if user.org_role != "owner":
        raise HTTPException(status_code=403, detail="requires organization owner")
    return user


def require_platform_admin(user: UserDTO = Depends(get_current_user)) -> UserDTO:
    """Instance-operator gate for platform-level shared assets (agent prompts,
    run policies, platform config, shared LLM providers, GitHub App
    credentials). Org-scoped admins are NOT platform admins — the flag comes
    from the Zitadel project role `admin` (or no-auth/shared-token mode)."""
    if not user.is_platform_admin:
        raise HTTPException(status_code=403, detail="requires platform administrator")
    return user


@lru_cache(maxsize=1)
def get_repository_service() -> RepositoryService:
    return RepositoryService()


@lru_cache(maxsize=1)
def get_github_service() -> GitHubService:
    return GitHubService()


@lru_cache(maxsize=1)
def get_llm_provider_service() -> LLMProviderService:
    return LLMProviderService()


def get_metrics_service() -> MetricsService:
    return MetricsService()


@lru_cache(maxsize=1)
def get_sandbox_service() -> SandboxService:
    return SandboxService()


