"""Pure-Python test: dedupe_key stability + collisions."""

from domains.findings.schemas import normalize_tags
from domains.findings.services.dedupe import build_dedupe_key


def test_same_inputs_yield_same_key():
    a = build_dedupe_key(
        repository_uid="r1",
        title="SQL injection in /users", top_path="api/users.py",
    )
    b = build_dedupe_key(
        repository_uid="r1",
        title="SQL injection in /users", top_path="api/users.py",
    )
    assert a == b


def test_normalisation_drops_numbers_and_case():
    a = build_dedupe_key(
        repository_uid="r1",
        title="SQL injection at line 42 in /users", top_path="api/users.py",
    )
    b = build_dedupe_key(
        repository_uid="r1",
        title="sql injection at line 99 in users",
        top_path="api/users.py",
    )
    assert a == b


def test_different_repository_yields_different_key():
    a = build_dedupe_key(
        repository_uid="r1", title="t", top_path="p",
    )
    b = build_dedupe_key(
        repository_uid="r2", title="t", top_path="p",
    )
    assert a != b


def test_different_top_path_yields_different_key():
    a = build_dedupe_key(
        repository_uid="r1",
        title="t", top_path="api/users.py",
    )
    b = build_dedupe_key(
        repository_uid="r1",
        title="t", top_path="api/admin.py",
    )
    assert a != b


def test_missing_optional_fields_dont_crash():
    k = build_dedupe_key(
        repository_uid="", title="", top_path="",
    )
    assert isinstance(k, str) and len(k) == 24


def test_normalize_tags_dedupes_and_normalizes():
    assert normalize_tags(["Security", "security", " Flaky Test ", ""]) == [
        "security",
        "flaky-test",
    ]


def test_normalize_tags_handles_none():
    assert normalize_tags(None) == []
