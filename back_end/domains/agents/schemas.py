"""Agent + ScheduledAgent DTOs."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, Field


class Produces(StrEnum):
    FINDINGS = "findings"
    ANSWER = "answer"
    DOCUMENTATION = "documentation"
    DOC_TREE = "doc-tree"
    ANALYSIS = "analysis"
    REVIEW_VERDICT = "review-verdict"
    VERIFICATION = "verification"
    CODE_CHANGES = "code-changes"


TRIGGER_MANUAL = ""
TRIGGER_ON_EVENT = "on-event"
TRIGGER_CRON_PREFIX = "cron:"


def parse_trigger(value: str | None) -> tuple[str, str]:
    """Return (kind, payload) for a ScheduledAgent trigger string.

    kind ∈ {"manual", "on-event", "cron"}; payload is the cron expression
    (empty otherwise). Raises ValueError on a "cron:" prefix with no
    expression.
    """
    raw = (value or "").strip()
    if not raw:
        return ("manual", "")
    if raw == TRIGGER_ON_EVENT:
        return ("on-event", "")
    if raw.startswith(TRIGGER_CRON_PREFIX):
        expr = raw[len(TRIGGER_CRON_PREFIX) :].strip()
        if not expr:
            raise ValueError("cron trigger requires a crontab expression after 'cron:'")
        return ("cron", expr)
    raise ValueError(f"unknown trigger format: {raw!r}")


class AgentDTO(BaseModel):
    uid: str
    title: str
    description: str = ""
    prompt: str = ""
    produces: str = "findings"
    default_effort: str = "normal"
    # "" = inherit from the effort tier | low | medium | high.
    reasoning: str = ""
    tags: list[str] = Field(default_factory=list)
    provenance: str = "user"  # system | user | imported
    # Stable slug for system rows ("ask", "review-guidance", "audit-stale" …)
    # derived from source_url; "" for user rows.
    key: str = ""
    source_url: str = ""
    source_commit: str = ""
    rev: int = 0
    # True when the caller's org has an active override of this system agent.
    has_org_override: bool = False
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CreateAgentRequest(BaseModel):
    title: str
    description: str = ""
    prompt: str = ""
    produces: str = "findings"
    default_effort: str = "normal"
    reasoning: str = ""
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True


class UpdateAgentRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    produces: Optional[str] = None
    default_effort: Optional[str] = None
    reasoning: Optional[str] = None
    tags: Optional[list[str]] = None
    enabled: Optional[bool] = None


class AgentRevisionDTO(BaseModel):
    uid: str
    agent_uid: str
    org_uid: str = ""
    rev: int
    mode: str = "replace"
    body: str = ""
    enabled: bool = True
    author_uid: str = ""
    created_at: Optional[datetime] = None


class SaveOverrideRequest(BaseModel):
    """PUT /agents/{uid}/override — the org's tuning of a system agent."""

    mode: str = "append"  # append | replace
    body: str = ""
    enabled: bool = True


class RevertRequest(BaseModel):
    rev: int


class PreviewOverrideRequest(BaseModel):
    mode: str = "append"
    body: str = ""


class AgentDispatchRequest(BaseModel):
    """POST /agents/{uid}/runs — ad-hoc run of an agent on a repository."""

    repository_uid: str
    effort: Optional[str] = None
    target: dict[str, Any] = Field(default_factory=dict)


class ScheduledAgentDTO(BaseModel):
    uid: str
    agent_uid: str
    repository_uid: str
    title: str = ""
    trigger: str = ""
    target: dict[str, Any] = Field(default_factory=dict)
    effort: str = ""
    run_policy_uid: str | None = None
    autonomy: str = "ask-before-run"
    enabled: bool = True
    provenance: str = "user"
    last_scheduled_at: Optional[datetime] = None
    # Denormalized from the bound Agent for list surfaces.
    agent_title: str = ""
    agent_produces: str = "findings"
    agent_key: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CreateScheduledAgentRequest(BaseModel):
    agent_uid: str
    repository_uid: str
    title: str = ""
    trigger: str = ""
    target: dict[str, Any] = Field(default_factory=dict)
    effort: str = ""
    run_policy_uid: str | None = None
    # validation_alias keeps pre-rename API clients ("compute_dial") working.
    autonomy: str = Field(
        default="ask-before-run",
        validation_alias=AliasChoices("autonomy", "compute_dial"),
    )
    enabled: bool = True


class UpdateScheduledAgentRequest(BaseModel):
    """PATCH /scheduled-agents/{uid} — None = leave unchanged."""

    title: Optional[str] = None
    trigger: Optional[str] = None
    target: Optional[dict[str, Any]] = None
    effort: Optional[str] = None
    run_policy_uid: Optional[str] = None
    autonomy: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("autonomy", "compute_dial")
    )
    enabled: Optional[bool] = None


class ImportEccResult(BaseModel):
    imported: int
    skipped_user_edited: int
    source_commit: str
    errors: list[str] = Field(default_factory=list)
