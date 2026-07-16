"""Repository routes — list, get, create, update, delete + kill switches + file reads."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from api.dependencies import (
    get_current_user,
    get_repository_service,
    require_role,
)
from domains.repositories.schemas import (
    CreateRepositoryRequest,
    FileContentDTO,
    RepositoryDTO,
    SetKillSwitchRequest,
    UpdateRepositoryRequest,
)
from domains.repositories.services.github_service import GitHubService
from domains.repositories.services.repository_service import RepositoryService
from domains.users.schemas import UserDTO
from infrastructure.audit import write_audit
from infrastructure.git_providers import get_provider_client
from infrastructure.kill_switch import (
    set_repo_kill_switch,
)

router = APIRouter(prefix="/api/v1/repositories", tags=["repositories"])


@router.get("", response_model=list[RepositoryDTO], operation_id="opensweep_list_repositories")
async def list_repositories(
    svc: RepositoryService = Depends(get_repository_service),
    user: UserDTO = Depends(get_current_user),
):
    return await svc.list_repositories(user.org_uid)


@router.get(
    "/by-slug/{slug}",
    response_model=RepositoryDTO,
    operation_id="opensweep_get_repository_by_slug",
)
async def get_repository_by_slug(
    slug: str,
    svc: RepositoryService = Depends(get_repository_service),
    user: UserDTO = Depends(get_current_user),
):
    return await svc.get_repository_by_slug(slug, user.org_uid)


@router.get("/{uid}", response_model=RepositoryDTO, operation_id="opensweep_get_repository")
async def get_repository(
    uid: str,
    svc: RepositoryService = Depends(get_repository_service),
    user: UserDTO = Depends(get_current_user),
):
    return await svc.get_repository(uid, user.org_uid)


# ── File reads (GitHub contents API) ────────────────────────────────────────
# Relocated from the retired api/v1/local_git.py. Path + auto-generated
# operation_id are preserved — front_end CodeSnippetViewer.vue calls this route.


_EXT_LANG = {
    ".py": "python", ".js": "javascript", ".jsx": "jsx", ".ts": "typescript",
    ".tsx": "tsx", ".vue": "vue", ".go": "go", ".rs": "rust", ".java": "java",
    ".rb": "ruby", ".php": "php", ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
    ".cs": "csharp", ".kt": "kotlin", ".swift": "swift", ".scala": "scala",
    ".sh": "bash", ".zsh": "bash", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".json": "json", ".md": "markdown", ".html": "html", ".css": "css",
    ".scss": "scss", ".sql": "sql", ".dockerfile": "dockerfile",
}


def _guess_language(path: str) -> str | None:
    from pathlib import PurePosixPath
    name = PurePosixPath(path).name.lower()
    if name == "dockerfile":
        return "dockerfile"
    suffix = PurePosixPath(path).suffix.lower()
    return _EXT_LANG.get(suffix)


def _slice_lines(content: str, start: int | None, end: int | None) -> tuple[str, int, int, int]:
    lines = content.splitlines()
    total = len(lines)
    s = max(1, start or 1)
    e = min(total, end or total)
    if e < s:
        e = s
    sliced = "\n".join(lines[s - 1:e])
    return sliced, total, s, e


@router.get("/{uid}/file", response_model=FileContentDTO)
async def repository_file(
    uid: str,
    path: str = Query(..., description="Repo-relative file path"),
    ref: str | None = Query(None, description="Branch/sha"),
    start_line: int | None = Query(None, ge=1),
    end_line: int | None = Query(None, ge=1),
    repos: RepositoryService = Depends(get_repository_service),
    user: UserDTO = Depends(get_current_user),
):
    repo = await repos.get_repository(uid, user.org_uid)
    if not (repo.github_owner and repo.github_repo):
        raise HTTPException(status_code=400, detail="Repository has no github_owner/github_repo configured")
    # Repo-scoped credential: App installation token when the App covers this
    # repo, else the PAT default client.
    gh = GitHubService(get_provider_client(repo))
    result = await gh.get_file_contents(repo.github_owner, repo.github_repo, path, ref=ref)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"File not available from GitHub: {path} "
                "(check the GitHub App installation covers this repo — or GITHUB_TOKEN "
                "is set — and the path exists on the target ref)"
            ),
        )
    content, bytes_total = result
    sliced, total_lines, s, e = _slice_lines(content, start_line, end_line)
    return FileContentDTO(
        path=path, content=sliced, language=_guess_language(path),
        total_lines=total_lines, start_line=s, end_line=e,
        truncated=False, source="github", bytes_total=bytes_total,
    )


@router.post("", response_model=RepositoryDTO, status_code=201)
async def create_repository(
    req: CreateRepositoryRequest,
    svc: RepositoryService = Depends(get_repository_service),
    user: UserDTO = Depends(require_role("maintainer")),
):
    return await svc.create(req, user.org_uid)


@router.patch("/{uid}", response_model=RepositoryDTO)
async def update_repository(
    uid: str,
    req: UpdateRepositoryRequest,
    svc: RepositoryService = Depends(get_repository_service),
    user: UserDTO = Depends(require_role("maintainer")),
):
    return await svc.update(uid, req, user.org_uid)


@router.delete("/{uid}", status_code=204)
async def delete_repository(
    uid: str,
    svc: RepositoryService = Depends(get_repository_service),
    user: UserDTO = Depends(require_role("maintainer")),
):
    await svc.delete(uid, user.org_uid)
    return Response(status_code=204)


@router.post(
    "/{uid}/kill-switch",
    response_model=RepositoryDTO,
    operation_id="opensweep_set_repo_kill_switch",
)
async def toggle_repo_kill_switch(
    uid: str,
    req: SetKillSwitchRequest,
    svc: RepositoryService = Depends(get_repository_service),
    user: UserDTO = Depends(require_role("maintainer")),
):
    from domains.tenancy import require_repo_in_org

    await require_repo_in_org(uid, user.org_uid)
    ok = await set_repo_kill_switch(uid, req.active)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Repository {uid} not found")
    await write_audit(
        kind="repository.kill_switch_changed",
        subject_uid=uid,
        subject_type="Repository",
        actor_uid=user.uid,
        payload={"active": req.active},
    )
    return await svc.get_repository(uid, user.org_uid)
