"""Read-only artifact routes.

Tenancy: artifact URIs are opensweep-artifact://<repository_uid>/<run_uid>/…
(infrastructure/artifact_store.py) — the embedded repository is org-checked
before the blob is served.
"""

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user
from domains.tenancy import require_repo_in_org
from domains.users.schemas import UserDTO
from infrastructure import artifact_store

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])

_SCHEME_PREFIX = "opensweep-artifact://"


def _repository_uid_of(uri: str) -> str:
    if not uri.startswith(_SCHEME_PREFIX):
        return ""
    parts = uri[len(_SCHEME_PREFIX):].split("/")
    return parts[0] if parts else ""


@router.get("", operation_id="opensweep_get_artifact")
async def get_artifact(uri: str, user: UserDTO = Depends(get_current_user)):
    await require_repo_in_org(_repository_uid_of(uri), user.org_uid)
    data = artifact_store.get(uri)
    if data is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {
        "uri": uri,
        "text": data.decode("utf-8", errors="replace"),
        "bytes": len(data),
    }
