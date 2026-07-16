"""Slack integration — per-org SlackConnection + SlackNotificationRule."""

VERSION = 7
NAME = "slack-integration"

SCHEMA_UP: list[str] = [
    "CREATE CONSTRAINT slack_connection_uid IF NOT EXISTS FOR (n:SlackConnection) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT slack_connection_team IF NOT EXISTS FOR (n:SlackConnection) REQUIRE n.team_id IS UNIQUE",
    "CREATE CONSTRAINT slack_rule_uid IF NOT EXISTS FOR (n:SlackNotificationRule) REQUIRE n.uid IS UNIQUE",
    "CREATE INDEX slack_connection_org IF NOT EXISTS FOR (n:SlackConnection) ON (n.org_uid)",
    "CREATE INDEX slack_rule_org IF NOT EXISTS FOR (n:SlackNotificationRule) ON (n.org_uid)",
    "CREATE INDEX slack_rule_event_type IF NOT EXISTS FOR (n:SlackNotificationRule) ON (n.event_type)",
]
SCHEMA_DOWN: list[str] = [
    "DROP CONSTRAINT slack_connection_uid IF EXISTS",
    "DROP CONSTRAINT slack_connection_team IF EXISTS",
    "DROP CONSTRAINT slack_rule_uid IF EXISTS",
    "DROP INDEX slack_connection_org IF EXISTS",
    "DROP INDEX slack_rule_org IF EXISTS",
    "DROP INDEX slack_rule_event_type IF EXISTS",
]
UP: list[str] = []
DOWN: list[str] = [
    # A rolled-back image knows nothing about these nodes — remove them so a
    # later re-upgrade starts from a clean install flow.
    "MATCH (n:SlackNotificationRule) DELETE n",
    "MATCH (n:SlackConnection) DELETE n",
]
