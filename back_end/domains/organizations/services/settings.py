"""Per-org settings: parse the JSON blob and resolve it from a repository.

Settings live as a JSON string on Organization.settings_json (multi-tenancy
phase 2). Every domain node reaches its org via Repository.org_uid, so callers
that only hold a repository_uid (e.g. a refine run) go through
`get_settings_for_repo`. Parsing never raises — a missing or malformed blob
falls back to defaults so a bad write can't wedge a run.
"""

from __future__ import annotations

from domains.organizations.models import Organization
from domains.organizations.schemas import OrgSettingsDTO
from logging_config import logger


def parse_settings(settings_json: str | None) -> OrgSettingsDTO:
    if not settings_json:
        return OrgSettingsDTO()
    try:
        return OrgSettingsDTO.model_validate_json(settings_json)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"malformed org settings_json, using defaults: {type(exc).__name__}: {exc}",
            extra={"tag": "org-settings"},
        )
        return OrgSettingsDTO()


async def get_org_settings(org_uid: str) -> OrgSettingsDTO:
    org = await Organization.nodes.get_or_none(uid=org_uid)
    return parse_settings(org.settings_json if org else None)


async def get_settings_for_repo(repository_uid: str) -> OrgSettingsDTO:
    """Settings of the org that owns `repository_uid` (defaults if unknown)."""
    from domains.repositories.models import Repository

    repo = await Repository.nodes.get_or_none(uid=repository_uid)
    if repo is None:
        return OrgSettingsDTO()
    return await get_org_settings(repo.org_uid)
