"""LLM provider route surface — the onboarding /status probe is mounted and
declared before the /{uid} catch-all (mirrors the openapi-schema pattern in
test_phase3_routes.py)."""

from api.v1.llm_providers import router
from app import app


def test_status_route_is_mounted():
    paths = set(app.openapi().get("paths", {}).keys())
    assert "/api/v1/llm-providers/status" in paths
    assert "/api/v1/llm-providers/{uid}" in paths


def test_status_is_declared_before_the_uid_route():
    # FastAPI matches in declaration order — /status must never be captured
    # as a provider uid by the /{uid} route.
    paths = [r.path for r in router.routes]
    assert paths.index("/api/v1/llm-providers/status") < paths.index(
        "/api/v1/llm-providers/{uid}"
    )
