import logging
import sys

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.v1.platform_tools import CreateFindingRequest
from domains.platform_tools.create_finding import create_finding
from logging_config import OpenSweepFormatter


def test_create_finding_request_validates_enum_fields():
    with pytest.raises(ValidationError) as exc_info:
        CreateFindingRequest(
            repository_uid="repo-1",
            severity="catastrophic",
            title="Bad severity value should not reach the tool body",
        )

    errors = exc_info.value.errors()
    assert errors[0]["loc"] == ("severity",)


def test_create_finding_request_accepts_free_text_tags():
    req = CreateFindingRequest(
        repository_uid="repo-1",
        tags=["security", "anything-goes"],
        title="Tags are free text, not an enum",
    )
    assert req.tags == ["security", "anything-goes"]


async def test_create_finding_rejects_bad_enum_before_persistence():
    with pytest.raises(HTTPException) as exc_info:
        await create_finding(
            repository_uid="repo-1",
            tags=["security"],
            kind="vulnerability",
            title="Bad kind value should not reach persistence",
        )

    assert exc_info.value.status_code == 422
    assert "invalid kind" in exc_info.value.detail


def test_opensweep_formatter_keeps_exception_traceback():
    formatter = OpenSweepFormatter()
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record = logging.getLogger("opensweep.test").makeRecord(
            "opensweep.test",
            logging.ERROR,
            __file__,
            1,
            "tool failed",
            args=(),
            exc_info=sys.exc_info(),
        )

    formatted = formatter.format(record)
    assert "tool failed" in formatted
    assert "Traceback (most recent call last)" in formatted
    assert "RuntimeError: boom" in formatted
