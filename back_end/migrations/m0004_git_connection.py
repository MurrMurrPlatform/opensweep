"""GithubInstallation → GitConnection (git-provider abstraction).

The installation→org tenancy link generalizes to a provider-agnostic
GitConnection node: provider="github", external_id = the App installation id
stringified, display_name = the old `account`. Repository nodes gain a
`provider` property (backfilled to "github").

UP keeps the legacy installation_id/account properties on the relabeled
nodes so DOWN is lossless: a deployment rollback relabels them back and the
older image's code (which reads installation_id) sees exactly what it wrote.
"""

VERSION = 4
NAME = "git-connection"

SCHEMA_UP: list[str] = [
    "DROP CONSTRAINT github_installation_id IF EXISTS",
    "DROP INDEX github_installation_org IF EXISTS",
    "CREATE CONSTRAINT git_connection_uid IF NOT EXISTS FOR (n:GitConnection) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT git_connection_external_id IF NOT EXISTS FOR (n:GitConnection) REQUIRE n.external_id IS UNIQUE",
    "CREATE INDEX git_connection_org IF NOT EXISTS FOR (n:GitConnection) ON (n.org_uid)",
    "CREATE INDEX git_connection_provider IF NOT EXISTS FOR (n:GitConnection) ON (n.provider)",
    "CREATE INDEX repo_provider IF NOT EXISTS FOR (n:Repository) ON (n.provider)",
]
SCHEMA_DOWN: list[str] = [
    "DROP CONSTRAINT git_connection_uid IF EXISTS",
    "DROP CONSTRAINT git_connection_external_id IF EXISTS",
    "DROP INDEX git_connection_org IF EXISTS",
    "DROP INDEX git_connection_provider IF EXISTS",
    "DROP INDEX repo_provider IF EXISTS",
    "CREATE CONSTRAINT github_installation_id IF NOT EXISTS FOR (n:GithubInstallation) REQUIRE n.installation_id IS UNIQUE",
    "CREATE INDEX github_installation_org IF NOT EXISTS FOR (n:GithubInstallation) ON (n.org_uid)",
]
UP: list[str] = [
    # Relabel + generalize; installation_id/account stay in place for a
    # lossless DOWN.
    "MATCH (g:GithubInstallation) "
    "SET g:GitConnection, "
    "g.uid = coalesce(g.uid, randomUUID()), "
    "g.provider = 'github', "
    "g.external_id = toString(g.installation_id), "
    "g.display_name = coalesce(g.account, ''), "
    "g.linked_by = coalesce(g.linked_by, '') "
    "REMOVE g:GithubInstallation",
    "MATCH (r:Repository) WHERE r.provider IS NULL SET r.provider = 'github'",
]
DOWN: list[str] = [
    "MATCH (g:GitConnection) "
    "SET g:GithubInstallation, "
    "g.installation_id = coalesce(g.installation_id, toInteger(g.external_id)), "
    "g.account = coalesce(g.account, g.display_name) "
    "REMOVE g:GitConnection",
    "MATCH (r:Repository) REMOVE r.provider",
]
