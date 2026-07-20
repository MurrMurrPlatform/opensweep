"""Lens routes — list/read for everyone, tuning for platform admins.

Lenses are platform-level rows (no repository dimension), so reads carry no
tenancy filter; edits follow the run-policies pattern (platform admin only).
"""

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_current_user, require_platform_admin
from domains.lenses.schemas import LensDTO, UpdateLensRequest
from domains.lenses.services import lens_service
from domains.users.schemas import UserDTO

router = APIRouter(prefix="/api/v1/lenses", tags=["lenses"])


@router.get("", response_model=list[LensDTO], operation_id="opensweep_list_lenses")
async def list_lenses(
    enabled_only: bool = Query(False),
    user: UserDTO = Depends(get_current_user),
):
    return [lens_service.to_dto(lens) for lens in await lens_service.list_lenses(enabled_only=enabled_only)]


@router.get("/{key}", response_model=LensDTO, operation_id="opensweep_get_lens")
async def get_lens(key: str, user: UserDTO = Depends(get_current_user)):
    return lens_service.to_dto(await lens_service.get_by_key(key))


@router.patch("/{key}", response_model=LensDTO, operation_id="opensweep_update_lens")
async def update_lens(
    key: str,
    req: UpdateLensRequest,
    user: UserDTO = Depends(require_platform_admin),
):
    return await lens_service.update(key, req, actor_uid=user.uid)
