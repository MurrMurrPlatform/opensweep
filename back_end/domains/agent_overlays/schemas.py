"""Org agent overlay DTOs."""

from datetime import datetime

from pydantic import BaseModel


class OverlayDTO(BaseModel):
    uid: str
    playbook: str
    mode: str = "append"
    body: str = ""
    enabled: bool = True
    rev: int = 0
    updated_by: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PlatformBaseDTO(BaseModel):
    """Read-only preview of the seeded platform base for a playbook."""

    uid: str = ""
    title: str = ""
    body: str = ""
    enabled: bool = True
    source_url: str = ""


class PlaybookOverlayStatusDTO(BaseModel):
    playbook: str
    platform: PlatformBaseDTO | None = None  # None: base row deleted
    overlay: OverlayDTO | None = None  # None: org runs platform defaults


class OverlayRevisionDTO(BaseModel):
    uid: str
    playbook: str
    rev: int
    mode: str = "append"
    body: str = ""
    enabled: bool = True
    author_uid: str = ""
    created_at: datetime | None = None


class UpsertOverlayRequest(BaseModel):
    mode: str = "append"  # append | replace
    body: str = ""
    enabled: bool = True


class RevertOverlayRequest(BaseModel):
    rev: int


class PreviewOverlayRequest(BaseModel):
    """Draft overlay — composed but never persisted."""

    mode: str = "append"
    body: str = ""


class PreviewOverlayResponse(BaseModel):
    playbook: str
    mode: str
    prompt: str
