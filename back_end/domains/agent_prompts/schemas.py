"""AgentPrompt DTOs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AgentPromptDTO(BaseModel):
    uid: str
    title: str
    description: str = ""
    body: str = ""
    default_job_type: str = "audit"
    default_scope: str = "repository"
    default_effort: str = "normal"
    tags: list[str] = Field(default_factory=list)
    source: str = "user"
    source_url: str = ""
    source_commit: str = ""
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CreateAgentPromptRequest(BaseModel):
    title: str
    description: str = ""
    body: str = ""
    default_job_type: str = "audit"
    default_scope: str = "repository"
    default_effort: str = "normal"
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True


class UpdateAgentPromptRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    body: Optional[str] = None
    default_job_type: Optional[str] = None
    default_scope: Optional[str] = None
    default_effort: Optional[str] = None
    tags: Optional[list[str]] = None
    enabled: Optional[bool] = None


class ImportEccResult(BaseModel):
    imported: int
    skipped_user_edited: int
    source_commit: str
    errors: list[str] = Field(default_factory=list)
