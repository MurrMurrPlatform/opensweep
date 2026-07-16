"""Platform tool: ask_question.

Append one unresolved question to the deep-scan Analysis — something the agent
cannot resolve from the code alone and needs a human to answer (production
data, runtime metrics, product intent, deployment context, …). Questions are
answerable in the UI; answered ones feed a refine-with-answers re-scan.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from domains.analysis.services.analysis_service import get_or_create_analysis


async def ask_question(
    *,
    repository_uid: str,
    source_run_uid: str,
    question: str,
    why_it_matters: str = "",
    category: str = "",
    executor: str = "",
) -> dict[str, Any]:
    if not (question or "").strip():
        raise HTTPException(status_code=422, detail="question must be non-empty")

    node = await get_or_create_analysis(
        repository_uid=repository_uid,
        source_run_uid=source_run_uid,
        executor=executor,
    )
    questions = list(node.questions or [])
    qid = uuid4().hex
    questions.append(
        {
            "uid": qid,
            "question": question.strip(),
            "why_it_matters": why_it_matters or "",
            "category": category or "",
            "status": "open",
            "answer": "",
            "answered_by": "",
            "answered_at": None,
        }
    )
    node.questions = questions
    node.updated_at = datetime.now(UTC)
    await node.save()
    return {"analysis_uid": node.uid, "question_uid": qid}
