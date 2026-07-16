"""Drop constraints/indexes for deleted node classes.

Branch / Commit / File (never-instantiated v1 repo-graph nodes) and
Knowledge / CoverageRecord (KNOWLEDGE_V3: replaced by Docs, Memories, and
Checked stamps) no longer exist in code — their constraints and indexes are
dead weight. neomodel_bootstrap no longer creates them; this migration
removes them from existing databases.

SCHEMA_DOWN recreates them so a deployment rollback to an older image (whose
bootstrap expects them) stays clean.
"""

VERSION = 2
NAME = "drop-dead-constraints"

SCHEMA_UP: list[str] = [
    "DROP CONSTRAINT branch_uid IF EXISTS",
    "DROP CONSTRAINT commit_sha IF EXISTS",
    "DROP CONSTRAINT file_uid IF EXISTS",
    "DROP CONSTRAINT coverage_uid IF EXISTS",
    "DROP CONSTRAINT knowledge_uid IF EXISTS",
    "DROP INDEX file_path IF EXISTS",
    "DROP INDEX knowledge_type IF EXISTS",
    "DROP INDEX knowledge_scope IF EXISTS",
    "DROP INDEX knowledge_status IF EXISTS",
    "DROP INDEX knowledge_provenance IF EXISTS",
]
SCHEMA_DOWN: list[str] = [
    "CREATE CONSTRAINT branch_uid IF NOT EXISTS FOR (n:Branch) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT commit_sha IF NOT EXISTS FOR (n:Commit) REQUIRE n.sha IS UNIQUE",
    "CREATE CONSTRAINT file_uid IF NOT EXISTS FOR (n:File) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT coverage_uid IF NOT EXISTS FOR (n:CoverageRecord) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT knowledge_uid IF NOT EXISTS FOR (n:Knowledge) REQUIRE n.uid IS UNIQUE",
    "CREATE INDEX file_path IF NOT EXISTS FOR (n:File) ON (n.path)",
    "CREATE INDEX knowledge_type IF NOT EXISTS FOR (n:Knowledge) ON (n.type)",
    "CREATE INDEX knowledge_scope IF NOT EXISTS FOR (n:Knowledge) ON (n.scope_uid)",
    "CREATE INDEX knowledge_status IF NOT EXISTS FOR (n:Knowledge) ON (n.status)",
    "CREATE INDEX knowledge_provenance IF NOT EXISTS FOR (n:Knowledge) ON (n.provenance)",
]
UP: list[str] = []
DOWN: list[str] = []
