"""Run carries an optional thread back-reference (unified dev flow Phase 1)."""

from domains.runs.models import Run


def test_run_has_thread_uid_property():
    # neomodel classes expose deflated property definitions on the class.
    assert "thread_uid" in Run.defined_properties(rels=False, aliases=False)


def test_thread_uid_defaults_to_empty():
    prop = Run.defined_properties(rels=False, aliases=False)["thread_uid"]
    assert prop.default == ""
