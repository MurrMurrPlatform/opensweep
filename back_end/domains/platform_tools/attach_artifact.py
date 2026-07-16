"""Platform tool: attach_artifact.

Non-patch supporting output: trace summaries, test logs, benchmarks,
screenshots, dependency graphs, reproduction notes, etc. Stored via the
artifact_store and recorded on the target's audit trail.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException

from infrastructure import artifact_store
from infrastructure.audit import write_audit

# Mirrors the resolver in api/v1/platform_tools.py (_artifact_target_repository_uid).
VALID_TARGET_TYPES = {"run", "finding", "doc", "memory", "ticket", "pull_request", "pullrequest"}


async def attach_artifact(
    *,
    target_uid: str,
    target_type: str,  # run | finding | doc | memory | ticket | pull_request
    artifact_type: str,
    content: bytes | str,
    repository_uid: Optional[str] = None,
    extension: str = "txt",
    summary: str = "",
    executor: str = "manual",
) -> dict[str, Any]:
    normalized = target_type.strip().lower()
    if normalized not in VALID_TARGET_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"unknown target_type '{target_type}' — must be one of: "
                "run, finding, doc, memory, ticket, pull_request"
            ),
        )
    uri = artifact_store.put(
        repository_uid=repository_uid or target_uid,
        run_uid=target_uid,
        content=content,
        artifact_type=artifact_type,
        extension=extension,
        summary=summary,
    )
    await write_audit(
        kind="artifact.attached",
        subject_uid=target_uid,
        subject_type=target_type,
        actor_uid=executor,
        payload={
            "artifact_type": artifact_type,
            "artifact_ref": uri,
            "summary": summary,
        },
    )
    return {"target_uid": target_uid, "artifact_ref": uri}
