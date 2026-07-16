"""Dashboard metric DTOs."""

from pydantic import BaseModel, Field


class FindingStatusCount(BaseModel):
    status: str
    count: int


class FindingTagCount(BaseModel):
    tag: str
    count: int


class RepoSummary(BaseModel):
    repository_uid: str
    repository_name: str
    repository_slug: str
    docs: int = 0
    open_findings: int = 0
    high_severity_findings: int = 0
    proposals: int = 0
    runs_last_24h: int = 0


class OverviewMetrics(BaseModel):
    repositories_github: int = 0
    total_docs: int = 0
    open_findings: int = 0
    high_severity_findings: int = 0
    proposals: int = 0
    runs_last_24h: int = 0
    finding_statuses: list[FindingStatusCount] = Field(default_factory=list)
    finding_tags: list[FindingTagCount] = Field(default_factory=list)
    repositories: list[RepoSummary] = Field(default_factory=list)
