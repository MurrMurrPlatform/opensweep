"""Investigation job types.

A job_type encodes **what kind of output** a saved Investigation produces.
Focus (security, tests, …) is not a taxonomy — it lives in the intent text
(KNOWLEDGE_V3_CHECKED.md §5).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobType:
    job_type: str
    title: str
    description: str
    intent: str


_JOB_TYPES: list[JobType] = [
    JobType(
        job_type="audit",
        title="Audit",
        description="File Findings against the target.",
        intent="Audit the target. File Findings with kind=defect|gap|improvement, evidence, affected paths, and severity. Focus on whatever the intent text emphasizes; otherwise cover correctness, security, tests, and maintainability broadly.",
    ),
    JobType(
        job_type="implement",
        title="Implement",
        description="Write-path run: implement a ticket's acceptance criteria in a write sandbox; the platform validates and pushes.",
        intent="Implement the ticket's acceptance criteria minimally in this working copy. Run the repository's test suites if discoverable, commit with conventional messages referencing the ticket, and finish with complete_run. Do not push — the platform validates and pushes.",
    ),
    JobType(
        job_type="sweep",
        title="Broad sweep",
        description="Wide audit across defects, tests, docs, and maintainability.",
        intent="Audit this target broadly: correctness/security defects, missing tests, stale source-repo docs, and maintainability improvements.",
    ),
    JobType(
        job_type="generate-docs",
        title="Generate documentation",
        description="Propose the documentation page tree; proposals only.",
        intent="Propose this repository's documentation page tree: architecture at the root, one folder per major subsystem, watch_paths on every page. Use propose_doc_edit per page. Do not file audit findings.",
    ),
    JobType(
        job_type="audit-stale",
        title="Audit stale code",
        description="Auto-select the stalest / never-checked doc pages and dispatch one scoped audit per page.",
        intent="Automatically audit the documentation pages whose code has moved since they were last checked (never-checked pages first). Each due tick selects up to target.limit pages and dispatches one watch_paths-scoped audit run per page.",
    ),
    JobType(
        job_type="document",
        title="Update documentation",
        description="Compare OpenSweep's Docs and Memories against the code; propose edits, prune stale notes.",
        intent="Compare this repository's Documentation pages and Memories against the current code. Read each page with read_doc, verify its claims against the code, and use propose_doc_edit where pages are wrong, missing, or bloated. Rewrite memories invalidated by code changes via write_memory. Prefer deleting stale prose over adding new prose. File Findings only for source-repository issues.",
    ),
]


def list_job_types() -> list[JobType]:
    return list(_JOB_TYPES)


def get_job_type(job_type: str) -> JobType | None:
    for jt in _JOB_TYPES:
        if jt.job_type == job_type:
            return jt
    return None
