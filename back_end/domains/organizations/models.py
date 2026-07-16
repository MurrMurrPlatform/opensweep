"""Organization nodes — the tenancy root (multi-tenancy phase 2).

OpenSweep owns organizations and memberships; the IdP (Zitadel) is authentication
only. A brand-new user's first login creates a personal org (they become its
owner) unless a pending OrgInvitation matches their email — then they join
the inviting org instead (domains/organizations/services/provisioning.py).

uid is a generated hex for OpenSweep-created orgs. Orgs provisioned before this
(phase-2 seam) used the Zitadel organization id as uid — those keep working:
uid is opaque, and every Repository carries org_uid, so org access checks
reduce to "is this repository in the caller's org" (domains/tenancy.py).

LOCAL_ORG_UID is the fixed org for the no-auth/shared-token single-tenant
mode — single-tenant operation is just multi-tenancy with one org.
"""

import uuid

from neomodel import (
    AsyncStructuredNode,
    DateTimeProperty,
    StringProperty,
)

LOCAL_ORG_UID = "local-org"

# org_role values — `owner` manages the org (rename, members, invitations);
# everyone else is a plain `member`. Orthogonal to the viewer/maintainer/admin
# capability role on User.
ORG_ROLES = {"owner", "member"}

INVITATION_STATUSES = {"pending", "accepted", "revoked"}


def new_org_uid() -> str:
    return uuid.uuid4().hex


class Organization(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)
    name = StringProperty(required=True)
    # User.uid of the creator — "" for orgs provisioned before ownership
    # existed (migration promotes an owner from the members instead).
    created_by = StringProperty(default="")
    # Per-org settings as a JSON blob (OrgSettingsDTO). Absent/"" ⇒ defaults;
    # see domains/organizations/services/settings.py for parse + resolve.
    settings_json = StringProperty(default="")
    created_at = DateTimeProperty(default_now=True)


class OrgInvitation(AsyncStructuredNode):
    """Email invitation into an org, created by an org owner.

    Matched case-insensitively against the invitee's email on their first
    OIDC login (they join `org_uid` instead of getting a personal org), or
    accepted explicitly by an already-registered user via /me/invitations.
    """

    uid = StringProperty(unique_index=True, default=new_org_uid)
    org_uid = StringProperty(required=True, index=True)
    email = StringProperty(required=True, index=True)  # stored lowercased
    role = StringProperty(default="maintainer")  # viewer | maintainer | admin
    status = StringProperty(default="pending", index=True)
    invited_by = StringProperty(default="")  # User.uid
    accepted_by = StringProperty(default="")  # User.uid once accepted
    created_at = DateTimeProperty(default_now=True)
    accepted_at = DateTimeProperty(default=None)


class GitConnection(AsyncStructuredNode):
    """Git-provider connection → org link (generalizes GithubInstallation).

    Each connection belongs to exactly one OpenSweep org. Two kinds:

    - kind="app": a GitHub App installation (the platform-level App serves
      every tenant; installs are linked when the install flow returns through
      the App's setup URL — state carries the org — or backfilled from
      repositories that already reference the installation). external_id is
      the installation id as a string. Rows created before `kind` existed
      have no kind property — read them as "app" (`kind or "app"`).
    - kind="pat": an org-supplied personal access token (the self-serve OSS
      path — domains/organizations/services/git_connections.py). The token
      is stored SEALED in token_sealed (infrastructure/secretbox.py);
      external_id is "pat:" + a token digest, which both satisfies the
      uniqueness constraint and blocks connecting the same token twice.

    external_id is unique across providers for now (no composite uniqueness
    in Neo4j Community edition — revisit at the second provider).
    """

    uid = StringProperty(unique_index=True, default=new_org_uid)
    org_uid = StringProperty(required=True, index=True)
    provider = StringProperty(default="github", index=True)
    kind = StringProperty(default="app", index=True)  # app | pat
    external_id = StringProperty(unique_index=True, required=True)
    display_name = StringProperty(default="")  # provider account login, informational
    # secretbox-sealed PAT — kind="pat" only, NEVER returned by any API.
    token_sealed = StringProperty(default="")
    linked_by = StringProperty(default="")  # User.uid
    created_at = DateTimeProperty(default_now=True)
