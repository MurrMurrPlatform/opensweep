"""Finding node — faceted output of a Run.

Bugs, security issues, gaps, refactors, proposals, and parse-fallback
observations all share this primitive. They differ only in their facets
(tags / kind / severity / effort / subtype). `affected_paths` is the code
anchor; doc pages relate to findings at read time via watch_paths overlap.
"""

from neomodel import (
    AsyncStructuredNode,
    DateTimeProperty,
    FloatProperty,
    JSONProperty,
    StringProperty,
)


class Finding(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)
    repository_uid = StringProperty(required=True, index=True)

    # Facets
    tags = JSONProperty(default=[])
    # Optional free-text labels for filtering ("security", "docs",
    # "structure", "flaky-test", …). Never a required taxonomy.
    kind = StringProperty(required=True, index=True)
    # defect | improvement | gap | proposal | observation | feature-idea
    severity = StringProperty(default="medium", index=True)
    # low | medium | high | critical
    effort = StringProperty(default="medium")
    # trivial | small | medium | large
    subtype = StringProperty(default="", index=True)
    # free-form, executor-extracted: "god-file", "missing-timeout",
    # "add-node", "split-node", "unparsed-executor-output", etc.

    title = StringProperty(required=True)
    confidence = FloatProperty(default=0.7)

    description = StringProperty(default="")
    # Detailed markdown analysis: what is wrong, where, and how it manifests.
    root_cause = StringProperty(default="")
    # Markdown: why the problem exists (the underlying mechanism, not the symptom).
    why_it_matters = StringProperty(default="")
    evidence = JSONProperty(default={})
    suggested_fix = StringProperty(default="")
    affected_paths = JSONProperty(default=[])

    dedupe_key = StringProperty(unique_index=True, required=True)

    # Provenance
    source_run_uid = StringProperty(index=True)
    executor = StringProperty(default="manual", index=True)
    # internal_llm | claude_code | codex | opencode | manual
    source_path = StringProperty(default="tool-call")
    # tool-call | parsed-blob | raw-derived
    parse_status = StringProperty(default="ok")
    # ok | degraded

    # Static-analysis provenance — set when the agent files this finding after
    # investigating a deterministic analyzer candidate (see execution/services/
    # static_analysis.py). Empty for findings the agent discovered on its own.
    detected_by_tool = StringProperty(default="", index=True)
    # ruff | vulture | deptry | semgrep | knip | "" (agent-discovered)
    detected_by_rule = StringProperty(default="")
    # the analyzer's rule/check id the candidate carried (e.g. "F821",
    # a semgrep check_id) — free-form, for cross-referencing the raw output.

    status = StringProperty(default="open", index=True)
    # open | acknowledged | wont-fix | fixed | accepted | superseded | dismissed

    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)


FINDING_KINDS = {"defect", "improvement", "gap", "proposal", "observation", "feature-idea"}

FINDING_SEVERITIES = {"low", "medium", "high", "critical"}

FINDING_EFFORTS = {"trivial", "small", "medium", "large"}

FINDING_STATUSES = {
    "open",
    "acknowledged",
    "wont-fix",
    "fixed",
    "accepted",
    "superseded",
    "dismissed",
}

FINDING_SOURCE_PATHS = {"tool-call", "parsed-blob", "raw-derived"}

FINDING_PARSE_STATUSES = {"ok", "degraded"}
