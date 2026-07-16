"""Pure-Python tests for the doc-page draft/verify intent builders
(KNOWLEDGE_V3).

The page IS the spec. The full DB-bound flow (loading the doc, dispatching
runs) is exercised in integration tests; here we just verify the intent
template shape so the LLM gets the right instructions.
"""

from domains.investigations.services.feature_specs import (
    _DRAFT_PAGE_INTENT,
    _VERIFY_PAGE_INTENT,
)


def test_draft_intent_proposes_a_doc_page():
    assert "{doc_summary}" in _DRAFT_PAGE_INTENT
    assert "{slug}" in _DRAFT_PAGE_INTENT
    assert "propose_doc_edit" in _DRAFT_PAGE_INTENT
    assert "watch_paths" in _DRAFT_PAGE_INTENT
    assert "file ordinary Findings" in _DRAFT_PAGE_INTENT


def test_verify_intent_files_findings_per_criterion():
    assert "{doc_summary}" in _VERIFY_PAGE_INTENT
    assert "{doc_body}" in _VERIFY_PAGE_INTENT
    assert "{slug}" in _VERIFY_PAGE_INTENT
    assert "create_finding" in _VERIFY_PAGE_INTENT
    assert "evidence.doc_slug" in _VERIFY_PAGE_INTENT
    assert "confirm_doc_current" in _VERIFY_PAGE_INTENT
    assert "edit the page" in _VERIFY_PAGE_INTENT
