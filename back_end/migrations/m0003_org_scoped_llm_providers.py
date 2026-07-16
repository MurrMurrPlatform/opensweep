"""LLM providers become strictly org-owned — no shared/platform scope.

Pre-tenancy (and formerly "shared") LLMProvider rows carried org_uid NULL or
"". The shared concept is gone: every provider must belong to exactly one
organization, so these rows are stamped to the local org.

Rationale: stamping to local-org (not copying per-org) avoids leaking
platform credentials into tenant-managed rows — a tenant admin must never
end up owning (and reading/rotating) a credential the platform operator
configured.

'local-org' is hardcoded == LOCAL_ORG_UID (domains.organizations.models);
migrations must be pure Cypher, so the constant cannot be imported here.
"""

VERSION = 3
NAME = "org-scoped-llm-providers"

SCHEMA_UP: list[str] = []
SCHEMA_DOWN: list[str] = []

UP: list[str] = [
    "MATCH (p:LLMProvider) WHERE p.org_uid IS NULL OR p.org_uid = '' "
    "SET p.org_uid = 'local-org', p.migrated_from_shared = true",
]
DOWN: list[str] = [
    "MATCH (p:LLMProvider {migrated_from_shared: true}) "
    "SET p.org_uid = '' REMOVE p.migrated_from_shared",
]
