"""Checked node — "last investigated" stamps (KNOWLEDGE_V3_CHECKED.md).

One stamp per scope per run. Replaces the CoverageRecord node×concern
matrix: the only question coverage must answer is "has this part of the
repo been looked at since it last changed", and that is derived at query
time from these stamps vs Doc.code_changed_at.
"""

from neomodel import (
    AsyncStructuredNode,
    DateTimeProperty,
    StringProperty,
)


class Checked(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)
    repository_uid = StringProperty(required=True, index=True)

    # Doc uid, or the repository uid for repo-wide runs.
    scope_uid = StringProperty(required=True, index=True)

    run_uid = StringProperty(required=True, index=True)

    revision = StringProperty(default="")  # commit sha inspected

    # clean | findings | failed — failed also covers cancelled/limit_exceeded:
    # for freshness purposes they all mean "this look did not complete".
    outcome = StringProperty(default="clean", index=True)

    checked_at = DateTimeProperty(default_now=True, index=True)


CHECKED_OUTCOMES = {"clean", "findings", "failed"}
