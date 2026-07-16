"""Organization / membership DTOs."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Policy for what a `refine` run does when it judges a Finding to be a false
# positive (not a real issue). Default is the conservative `annotate`: leave
# the status untouched and just record the doubt, so a human still decides.
RefineFalsePositivePolicy = Literal["annotate", "dismiss", "wont-fix"]


class OrgSettingsDTO(BaseModel):
    """Per-org configuration, persisted as JSON on Organization.settings_json."""

    refine_false_positive_policy: RefineFalsePositivePolicy = "annotate"


class OrganizationDTO(BaseModel):
    uid: str
    name: str
    created_at: datetime | None = None
    member_count: int = 0
    repository_count: int = 0
    is_owner: bool = False
    settings: OrgSettingsDTO = Field(default_factory=OrgSettingsDTO)


class UpdateOrganizationRequest(BaseModel):
    """Partial patch — send `name`, `settings`, or both."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    settings: OrgSettingsDTO | None = None


class OrgMemberDTO(BaseModel):
    uid: str
    email: str
    display_name: str
    role: str
    org_role: str
    created_at: datetime | None = None


class UpdateMemberRequest(BaseModel):
    role: str | None = None  # viewer | maintainer | admin
    org_role: str | None = None  # owner | member


class OrgInvitationDTO(BaseModel):
    uid: str
    email: str
    role: str
    status: str
    invited_by: str = ""
    created_at: datetime | None = None


class CreateInvitationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: str = "maintainer"

    @field_validator("email")
    @classmethod
    def _email_shape(cls, v: str) -> str:
        v = v.strip().lower()
        local, sep, domain = v.partition("@")
        if not sep or not local or "." not in domain or domain.startswith("."):
            raise ValueError("not a valid email address")
        return v


class MyInvitationDTO(BaseModel):
    """A pending invitation addressed to the current user's email."""

    uid: str
    org_uid: str
    org_name: str
    role: str
    created_at: datetime | None = None


class UpdateMeRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    onboarded: bool | None = None


class MeDTO(BaseModel):
    uid: str
    email: str
    display_name: str
    role: str
    org_role: str
    is_platform_admin: bool
    onboarded: bool
    org: OrganizationDTO
    pending_invitations: list[MyInvitationDTO] = []
