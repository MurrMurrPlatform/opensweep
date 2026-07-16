"""Tenancy scope for the platform-tool surface (multi-tenancy phase 2).

Two caller kinds reach /api/v1/platform-tools* (and the MCP mount):
  - Executors holding a `osrt_…` run token: TokenAuthMiddleware verified the
    token↔run binding and stashed `run_token_uid` in the scope. Their
    authority is exactly ONE run — every request must target that run's
    repository, nothing else.
  - Humans (OIDC / shared token): normal org rules — the target repository
    must be in the caller's org.

Both checks 404 on violation (existence never leaks).
"""

from fastapi import HTTPException
from starlette.requests import HTTPConnection

from domains.tenancy import require_repo_in_org
from domains.users.schemas import UserDTO


def _run_token_uid(connection: HTTPConnection) -> str:
    return (connection.scope.get("state") or {}).get("run_token_uid", "")


async def _run_repository_uid(run_uid: str) -> str:
    from domains.investigations.models import Run

    run = await Run.nodes.get_or_none(uid=run_uid)
    return run.repository_uid if run else ""


async def require_tool_repo_access(
    connection: HTTPConnection, user: UserDTO, repository_uid: str | None
) -> None:
    """Gate a platform-tool call that targets a repository."""
    token_run = _run_token_uid(connection)
    if token_run:
        run_repo = await _run_repository_uid(token_run)
        if not run_repo or (repository_uid or "") != run_repo:
            raise HTTPException(status_code=404, detail="not found")
        return
    await require_repo_in_org(repository_uid, user.org_uid)


async def require_tool_run_access(
    connection: HTTPConnection, user: UserDTO, run_uid: str
) -> None:
    """Gate a platform-tool call that targets a run (e.g. complete-run)."""
    token_run = _run_token_uid(connection)
    if token_run:
        if run_uid != token_run:
            raise HTTPException(status_code=404, detail="not found")
        return
    repo = await _run_repository_uid(run_uid)
    await require_repo_in_org(repo, user.org_uid)
