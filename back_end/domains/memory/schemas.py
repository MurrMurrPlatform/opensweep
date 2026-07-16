"""Memory DTOs."""

from datetime import datetime

from pydantic import BaseModel


class MemoryDTO(BaseModel):
    uid: str
    repository_uid: str
    anchor_uid: str = ""
    title: str
    body: str = ""
    source_run_uid: str = ""
    # Computed at read time: anchor's last_code_change_at > updated_at.
    possibly_stale: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
