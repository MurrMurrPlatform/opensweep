"""News + Interest DTOs."""

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field

from domains.findings.schemas import Effort, FindingKind, Severity


class NewsCategory(StrEnum):
    TRENDING_REPO = "trending-repo"
    AI_NEWS = "ai-news"
    FRAMEWORK = "framework"
    TECHNIQUE = "technique"
    RESEARCH = "research"
    TOOLING = "tooling"
    INDUSTRY = "industry"


class NewsStatus(StrEnum):
    NEW = "new"
    SAVED = "saved"
    DISMISSED = "dismissed"
    CONVERTED = "converted"


class NewsSource(StrEnum):
    SEARXNG = "searxng"
    GITHUB = "github"
    HACKERNEWS = "hackernews"
    ARXIV = "arxiv"
    TRENDSHIFT = "trendshift"
    MANUAL = "manual"


class NewsItemDTO(BaseModel):
    uid: str
    repository_uid: str

    title: str
    url: str = ""
    source: NewsSource = NewsSource.MANUAL
    category: NewsCategory = NewsCategory.INDUSTRY

    summary: str = ""
    relevance: str = ""
    tags: list[str] = Field(default_factory=list)
    published_at: Optional[datetime] = None

    status: NewsStatus = NewsStatus.NEW
    converted_finding_uid: str = ""

    dedupe_key: str
    source_run_uid: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CreateNewsItemRequest(BaseModel):
    """Direct API entry (humans). Agent-side filing goes through the
    create_news_item platform tool instead."""

    repository_uid: str
    title: str
    url: str = ""
    source: NewsSource = NewsSource.MANUAL
    category: NewsCategory = NewsCategory.INDUSTRY
    summary: str = ""
    relevance: str = ""
    tags: list[str] = Field(default_factory=list)
    published_at: Optional[datetime] = None
    source_run_uid: Optional[str] = None


class UpdateNewsItemRequest(BaseModel):
    """Human correction of a news item. Provenance (source, url, dedupe_key,
    source_run_uid) stays immutable; status has its own transition routes."""

    title: Optional[str] = None
    category: Optional[NewsCategory] = None
    summary: Optional[str] = None
    relevance: Optional[str] = None
    tags: Optional[list[str]] = None


class ConvertNewsRequest(BaseModel):
    """Human-only news → finding conversion parameters."""

    kind: FindingKind = FindingKind.FEATURE_IDEA
    severity: Severity = Severity.LOW
    effort: Effort = Effort.MEDIUM
    extra_tags: list[str] = Field(default_factory=list)


class InterestDTO(BaseModel):
    uid: str
    repository_uid: str
    title: str
    details: str = ""
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CreateInterestRequest(BaseModel):
    repository_uid: str
    title: str
    details: str = ""
    enabled: bool = True


class UpdateInterestRequest(BaseModel):
    title: Optional[str] = None
    details: Optional[str] = None
    enabled: Optional[bool] = None
