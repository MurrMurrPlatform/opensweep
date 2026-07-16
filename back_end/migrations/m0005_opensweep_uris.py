"""Koala → OpenSweep rebrand: rewrite seeded ``koala://`` resource URIs.

AgentPrompt rows seeded by the platform carry ``source_url`` values like
``koala://workflow/<stage>``; the seeders now emit ``opensweep://…``. This
migration rewrites the stored prefix so seed lookups (which match on
source_url) keep resolving the same rows instead of duplicating them.

DOWN restores the ``koala://`` prefix, so a rollback to a pre-rebrand image
(whose seeders look up ``koala://…``) finds its rows again — lossless.
"""

VERSION = 5
NAME = "opensweep-uris"

SCHEMA_UP: list[str] = []
SCHEMA_DOWN: list[str] = []

UP: list[str] = [
    "MATCH (p:AgentPrompt) WHERE p.source_url STARTS WITH 'koala://' "
    "SET p.source_url = 'opensweep://' + substring(p.source_url, size('koala://'))",
]
DOWN: list[str] = [
    "MATCH (p:AgentPrompt) WHERE p.source_url STARTS WITH 'opensweep://' "
    "SET p.source_url = 'koala://' + substring(p.source_url, size('opensweep://'))",
]
