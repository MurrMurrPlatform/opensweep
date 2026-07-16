"""Slack integration nodes — per-org workspace connection + notification rules.

One platform-level Slack app (SLACK_CLIENT_ID / SLACK_CLIENT_SECRET /
SLACK_SIGNING_SECRET) serves every tenant; each *connection* (an OAuth v2
install of that app into a Slack workspace) belongs to exactly one OpenSweep org.
team_id is unique — a workspace serves one org, first-wins, mirroring
GitConnection's installation semantics.

The bot token is sealed at rest via infrastructure/secretbox (enc:v1:…) —
never stored or logged in plaintext when OPENSWEEP_SECRETS_KEY is configured.
"""

import uuid

from neomodel import (
    AsyncStructuredNode,
    BooleanProperty,
    DateTimeProperty,
    StringProperty,
)


def new_slack_uid() -> str:
    return uuid.uuid4().hex


class SlackConnection(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, default=new_slack_uid)
    org_uid = StringProperty(required=True, index=True)
    team_id = StringProperty(unique_index=True, required=True)
    team_name = StringProperty(default="")
    bot_user_id = StringProperty(default="")
    # secretbox-sealed xoxb-… bot token (enc:v1: prefix when a key is set).
    bot_token_sealed = StringProperty(required=True)
    # Comma-separated OAuth scopes granted at install time, informational.
    scopes = StringProperty(default="")
    installed_by = StringProperty(default="")  # User.uid
    created_at = DateTimeProperty(default_now=True)


class SlackNotificationRule(AsyncStructuredNode):
    """event type → Slack channel routing, org-scoped.

    repository_uid narrows a rule to one repo; "" = every repo in the org.
    channel_name is a display snapshot from rule creation time — channel_id
    is what delivery posts to (survives channel renames).
    """

    uid = StringProperty(unique_index=True, default=new_slack_uid)
    org_uid = StringProperty(required=True, index=True)
    event_type = StringProperty(required=True, index=True)
    channel_id = StringProperty(required=True)
    channel_name = StringProperty(default="")
    repository_uid = StringProperty(default="")
    enabled = BooleanProperty(default=True)
    created_by = StringProperty(default="")  # User.uid
    created_at = DateTimeProperty(default_now=True)
