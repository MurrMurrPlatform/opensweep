"""Memory API — list/search + delete (KNOWLEDGE_V3).

No create/update endpoints: humans with durable guidance write a Doc, not a
Memory. Agents write memories through the write_memory platform tool.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_current_user, require_role
from domains.memory.schemas import MemoryDTO
from domains.memory.services import memory_service
from domains.tenancy import require_repo_in_org
from domains.users.schemas import UserDTO

router = APIRouter(prefix="/api/v1/memories", tags=["memories"])


@router.get("", operation_id="opensweep_list_memories")
async def list_memories(
    repository_uid: str = Query(...),
    anchor_uid: str = "",
    q: str = "",
    limit: int = 200,
    user: UserDTO = Depends(get_current_user),
) -> list[MemoryDTO]:
    await require_repo_in_org(repository_uid, user.org_uid)
    return await memory_service.list_memories(
        repository_uid=repository_uid, anchor_uid=anchor_uid, query=q, limit=limit
    )


@router.delete("/{uid}", operation_id="opensweep_delete_memory")
async def delete_memory(uid: str, user: UserDTO = Depends(require_role("maintainer"))) -> dict:
    from domains.memory.models import Memory

    m = await Memory.nodes.get_or_none(uid=uid)
    if m is None:
        raise HTTPException(status_code=404, detail=f"Memory {uid} not found")
    await require_repo_in_org(m.repository_uid, user.org_uid)
    await memory_service.delete_memory(uid, actor=user.uid)
    return {"status": "deleted"}
