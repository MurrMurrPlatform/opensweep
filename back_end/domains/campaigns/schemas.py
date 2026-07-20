"""Campaign DTOs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CampaignDTO(BaseModel):
    uid: str
    repository_uid: str
    title: str = ""
    status: str = "planning"
    template: str = "rotation"
    effort: str = ""
    lens_keys: list[str] = Field(default_factory=list)
    # Part dicts as stored: {idx, kind, title, scope_paths, doc_uids,
    # lens_keys, run_uid, state, file_count}.
    parts: list[dict] = Field(default_factory=list)
    max_parallel: int = 2
    created_by: str = ""
    trigger_provenance: str = ""
    summary: dict = Field(default_factory=dict)
    events: list[dict] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CreateCampaignRequest(BaseModel):
    template: str = "rotation"
    # Empty = every enabled lens; "focused" reads its focus lens from the
    # first entry.
    lens_keys: list[str] = Field(default_factory=list)
    # "" = default tiers (areas normal, global sweeps deep).
    effort: str = ""
    # Rotation only: how many areas this pass covers.
    k: int = 3
    max_parallel: int = 2
    title: str = ""
