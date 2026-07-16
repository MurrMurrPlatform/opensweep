"""Pydantic DTOs for the Slack integration API surface."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SlackEventTypeDTO(BaseModel):
    event_type: str
    label: str
    description: str


class SlackStatusDTO(BaseModel):
    # Platform-level: is the Slack app configured on this deployment at all?
    configured: bool
    connected: bool
    team_id: str = ""
    team_name: str = ""
    bot_user_id: str = ""
    scopes: list[str] = Field(default_factory=list)
    installed_by: str = ""
    event_types: list[SlackEventTypeDTO] = Field(default_factory=list)


class SlackChannelDTO(BaseModel):
    id: str
    name: str
    is_private: bool = False


class SlackRuleDTO(BaseModel):
    uid: str
    event_type: str
    channel_id: str
    channel_name: str = ""
    repository_uid: str = ""  # "" = all repositories in the org
    enabled: bool = True
    created_by: str = ""


class CreateSlackRuleRequest(BaseModel):
    event_type: str
    channel_id: str = Field(min_length=1)
    channel_name: str = ""
    repository_uid: str = ""
    enabled: bool = True


class UpdateSlackRuleRequest(BaseModel):
    event_type: str | None = None
    channel_id: str | None = None
    channel_name: str | None = None
    repository_uid: str | None = None
    enabled: bool | None = None


class SlackInstallUrlDTO(BaseModel):
    url: str
