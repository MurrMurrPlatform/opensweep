"""Pure unit tests for the ECC-prompt parser.

Avoids hitting Neo4j: tests the YAML+markdown parser and the tag
inference function. The full import flow is exercised end-to-end in the
manual smoke checklist.
"""

from domains.agents.services.ecc_import import (
    _extract_title,
    _infer_tags,
    _parse_markdown,
)


def test_parse_markdown_extracts_frontmatter_and_body():
    text = """---
description: Code review prompt
argument-hint: [pr-number]
---

# Code Review

Body content goes here.
"""
    meta, body = _parse_markdown(text)
    assert meta["description"] == "Code review prompt"
    # YAML parses `[pr-number]` as a one-element list.
    assert meta["argument-hint"] == ["pr-number"]
    assert "# Code Review" in body
    assert "Body content" in body


def test_parse_markdown_handles_no_frontmatter():
    text = "# Heading\n\nBody."
    meta, body = _parse_markdown(text)
    assert meta == {}
    assert body == text


def test_extract_title_from_h1():
    body = "Some intro\n\n# The Real Title\n\nMore content"
    assert _extract_title(body, "fallback") == "The Real Title"


def test_extract_title_falls_back_to_filename():
    assert _extract_title("no heading here", "code-review") == "code-review"


def test_infer_tags_security_scan():
    tags = _infer_tags("security-scan.md", {})
    assert "security" in tags


def test_infer_tags_test_coverage():
    tags = _infer_tags("test-coverage.md", {})
    assert "tests" in tags


def test_infer_tags_language_specific():
    tags = _infer_tags("python-review.md", {})
    assert "correctness" in tags
    assert any("python" in t for t in tags)


def test_infer_tags_refactor():
    tags = _infer_tags("refactor-clean.md", {})
    assert "maintainability" in tags
    assert "refactor" in tags


def test_agent_marker_added_for_agents():
    tags = _infer_tags("code-reviewer.md", {"tools": ["Read", "Grep"]})
    assert "agent" in tags
