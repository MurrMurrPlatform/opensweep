"""Codex-subscription credential lifecycle fields on LLMProvider.

Adds `credential_revision` (compare-and-swap fence for codex auth.json
write-back), `needs_reauth`, and `auth_state_uncertain`. Existing rows are
initialized to their neutral defaults so the write-back CAS and the DTO have
concrete values to read rather than NULL. See
docs/superpowers/specs/2026-07-20-codex-subscription-token-refresh-design.md.
"""

VERSION = 9
NAME = "codex-credential-state"

SCHEMA_UP: list[str] = []
SCHEMA_DOWN: list[str] = []

UP: list[str] = [
    "MATCH (p:LLMProvider) WHERE p.credential_revision IS NULL "
    "SET p.credential_revision = 0",
    "MATCH (p:LLMProvider) WHERE p.needs_reauth IS NULL "
    "SET p.needs_reauth = false",
    "MATCH (p:LLMProvider) WHERE p.auth_state_uncertain IS NULL "
    "SET p.auth_state_uncertain = false",
]
DOWN: list[str] = [
    "MATCH (p:LLMProvider) "
    "REMOVE p.credential_revision, p.needs_reauth, p.auth_state_uncertain",
]
