"""Event DTOs."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class EventDTO(BaseModel):
    uid: str
    kind: str
    subject_uid: Optional[str] = None
    subject_type: Optional[str] = None
    actor_uid: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime
