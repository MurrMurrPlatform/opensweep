"""Meta endpoints — health, version, current user, dashboard overview."""

from fastapi import APIRouter, Depends
from neomodel import adb

from api.dependencies import get_current_user, get_metrics_service
from domains.metrics.schemas import OverviewMetrics
from domains.metrics.services.metrics_service import MetricsService
from domains.users.schemas import UserDTO

router = APIRouter(prefix="/api/v1", tags=["meta"])


@router.get("/health")
async def health() -> dict:
    neo4j_ok = False
    try:
        await adb.cypher_query("RETURN 1")
        neo4j_ok = True
    except Exception:
        pass
    return {
        "status": "healthy" if neo4j_ok else "degraded",
        "services": {"neo4j": "ok" if neo4j_ok else "unavailable"},
    }


@router.get("/version")
async def version() -> dict:
    return {"name": "opensweep", "version": "0.1.0"}


@router.get("/me", response_model=UserDTO)
async def me(user: UserDTO = Depends(get_current_user)) -> UserDTO:
    return user


@router.get("/overview", response_model=OverviewMetrics)
async def overview(
    svc: MetricsService = Depends(get_metrics_service),
    user: UserDTO = Depends(get_current_user),
) -> OverviewMetrics:
    return await svc.overview(user.org_uid)
