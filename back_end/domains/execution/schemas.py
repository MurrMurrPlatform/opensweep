"""Workspace (sandbox) DTOs."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class SandboxStatus(StrEnum):
    PREPARING = "preparing"
    READY = "ready"
    FAILED = "failed"
    DESTROYED = "destroyed"


class SandboxDTO(BaseModel):
    uid: str
    repository_uid: str
    host_path: str
    container_path: str
    source_branch: str = "main"
    sandbox_branch: str = "opensweep/work"
    purpose: str = "discovery"  # discovery | write
    status: SandboxStatus
    created_at: datetime | None = None
    destroyed_at: datetime | None = None
    cleanup_after: datetime | None = None
    error: str = ""
