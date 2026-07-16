"""RunPolicy DTOs."""

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class OnExceed(StrEnum):
    ABORT = "abort"
    PAUSE_FOR_APPROVAL = "pause_for_approval"


class RunPolicyDTO(BaseModel):
    uid: str
    name: str = ""
    description: str = ""

    max_tokens: Optional[int] = None
    max_dollars: Optional[float] = None

    max_wall_seconds: Optional[int] = None
    max_tool_turns: Optional[int] = None
    max_files_touched: Optional[int] = None
    max_test_seconds: Optional[int] = None

    cloud_allowed: bool = False
    local_only: bool = False
    allowed_executors: list[str] = Field(default_factory=list)

    dry_run: bool = False
    warn_at_pct: int = 80
    on_exceed: OnExceed = OnExceed.ABORT

    daily_repo_run_count: Optional[int] = None
    daily_repo_wall_seconds: Optional[int] = None
    daily_repo_dollars: Optional[float] = None

    version: int = 1
    supersedes_uid: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CreateRunPolicyRequest(BaseModel):
    name: str
    description: str = ""

    max_tokens: Optional[int] = None
    max_dollars: Optional[float] = None

    max_wall_seconds: Optional[int] = None
    max_tool_turns: Optional[int] = None
    max_files_touched: Optional[int] = None
    max_test_seconds: Optional[int] = None

    cloud_allowed: bool = False
    local_only: bool = False
    allowed_executors: list[str] = Field(default_factory=list)

    dry_run: bool = False
    warn_at_pct: int = 80
    on_exceed: OnExceed = OnExceed.ABORT

    daily_repo_run_count: Optional[int] = None
    daily_repo_wall_seconds: Optional[int] = None
    daily_repo_dollars: Optional[float] = None

    @model_validator(mode="after")
    def _routing_is_consistent(self):
        # local_only is the stricter constraint; it implies cloud_allowed=False.
        # Accepting both as true is a footgun — the routing check then blocks
        # every cloud executor while the user thinks cloud is allowed.
        if self.local_only and self.cloud_allowed:
            raise ValueError(
                "RunPolicy: local_only=true implies cloud_allowed=false — "
                "cannot set both at once"
            )
        return self


class UpdateRunPolicyRequest(BaseModel):
    """Partial update — every field optional; only those sent are applied.

    Editing a policy in place keeps its uid (and therefore any runs that
    reference it) while letting an admin correct ceilings without the
    delete-and-recreate churn.
    """

    name: Optional[str] = None
    description: Optional[str] = None

    max_tokens: Optional[int] = None
    max_dollars: Optional[float] = None

    max_wall_seconds: Optional[int] = None
    max_tool_turns: Optional[int] = None
    max_files_touched: Optional[int] = None
    max_test_seconds: Optional[int] = None

    cloud_allowed: Optional[bool] = None
    local_only: Optional[bool] = None
    allowed_executors: Optional[list[str]] = None

    dry_run: Optional[bool] = None
    warn_at_pct: Optional[int] = None
    on_exceed: Optional[OnExceed] = None

    daily_repo_run_count: Optional[int] = None
    daily_repo_wall_seconds: Optional[int] = None
    daily_repo_dollars: Optional[float] = None
