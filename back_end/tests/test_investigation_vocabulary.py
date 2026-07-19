"""Pure-Python tests for Investigation vocabulary (KNOWLEDGE_V3)."""

import pytest

from domains.runs.schemas import parse_schedule
from domains.runs.services.job_types import get_job_type, list_job_types


def test_job_types_define_distinct_output_shapes():
    job_types = list_job_types()
    assert job_types
    assert all(jt.job_type for jt in job_types)
    ids = {jt.job_type for jt in job_types}
    assert ids == {
        "audit",
        "audit-stale",
        "implement",
        "sweep",
        "generate-docs",
        "document",
    }


def test_job_types_carry_intents_without_concern_taxonomy():
    for jt in list_job_types():
        assert jt.intent
        assert "propose_knowledge_update" not in jt.intent
        assert not hasattr(jt, "default_concerns")


def test_document_job_type_replaces_maintain_knowledge():
    assert get_job_type("maintain-knowledge") is None
    document = get_job_type("document")
    assert document is not None
    assert "propose_doc_edit" in document.intent
    assert "write_memory" in document.intent


def test_parse_schedule_handles_all_three_modes():
    assert parse_schedule("") == ("manual", "")
    assert parse_schedule(None) == ("manual", "")
    assert parse_schedule("on-event") == ("on-event", "")
    assert parse_schedule("cron:0 9 * * 1") == ("cron", "0 9 * * 1")
    with pytest.raises(ValueError):
        parse_schedule("cron:")
    with pytest.raises(ValueError):
        parse_schedule("nonsense")
