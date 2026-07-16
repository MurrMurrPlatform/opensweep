"""LLMProvider routes.

Tenancy: providers are strictly org-owned. Reads are scoped to the caller's
own org; writes need org role `admin` and are checked in the service — a
provider is manageable only by its owning org's admins.
"""

from fastapi import APIRouter, Depends

from api.dependencies import get_current_user, get_llm_provider_service, require_role
from domains.llm_providers.schemas import (
    KIND_CATALOG,
    CreateLLMProviderRequest,
    LLMProviderDTO,
    UpdateLLMProviderRequest,
)
from domains.llm_providers.services.llm_provider_service import LLMProviderService
from domains.users.schemas import UserDTO

router = APIRouter(prefix="/api/v1/llm-providers", tags=["llm-providers"])


@router.get("", response_model=list[LLMProviderDTO])
async def list_providers(
    svc: LLMProviderService = Depends(get_llm_provider_service),
    user: UserDTO = Depends(get_current_user),
):
    return await svc.list_providers(user.org_uid)


@router.get("/catalog")
async def list_kinds(user: UserDTO = Depends(get_current_user)):
    return [{"kind": k.value, **info} for k, info in KIND_CATALOG.items()]


@router.get("/active", response_model=LLMProviderDTO)
async def get_active_provider(
    svc: LLMProviderService = Depends(get_llm_provider_service),
    user: UserDTO = Depends(get_current_user),
):
    return await svc.get_active(user.org_uid)


# Declared BEFORE /{uid} so "status" is never captured as a provider uid.
@router.get("/status")
async def provider_status(
    svc: LLMProviderService = Depends(get_llm_provider_service),
    user: UserDTO = Depends(get_current_user),
):
    """Lightweight onboarding probe — returns 200 always: a fresh org's
    steady state (no providers yet) is not an error, unlike /active's 409."""
    return await svc.status(user.org_uid)


@router.get("/{uid}", response_model=LLMProviderDTO)
async def get_provider(
    uid: str,
    svc: LLMProviderService = Depends(get_llm_provider_service),
    user: UserDTO = Depends(get_current_user),
):
    return await svc.get(uid, user.org_uid)


@router.post("", response_model=LLMProviderDTO, status_code=201)
async def create_provider(
    req: CreateLLMProviderRequest,
    svc: LLMProviderService = Depends(get_llm_provider_service),
    user: UserDTO = Depends(require_role("admin")),
):
    return await svc.create(req, user=user)


@router.patch("/{uid}", response_model=LLMProviderDTO)
async def update_provider(
    uid: str,
    req: UpdateLLMProviderRequest,
    svc: LLMProviderService = Depends(get_llm_provider_service),
    user: UserDTO = Depends(require_role("admin")),
):
    return await svc.update(uid, req, user=user)


@router.delete("/{uid}", status_code=204)
async def delete_provider(
    uid: str,
    svc: LLMProviderService = Depends(get_llm_provider_service),
    user: UserDTO = Depends(require_role("admin")),
):
    await svc.delete(uid, user=user)


@router.post("/{uid}/check", response_model=LLMProviderDTO)
async def check_provider(
    uid: str,
    svc: LLMProviderService = Depends(get_llm_provider_service),
    user: UserDTO = Depends(require_role("admin")),
):
    return await svc.check_health(uid, user=user)
