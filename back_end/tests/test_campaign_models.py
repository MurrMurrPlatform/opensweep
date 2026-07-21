"""Campaign status state machine.

Pure tests, mirroring tests/test_thread_transitions.py: the full legality
matrix spelled out pairwise so a regression in either the dict or the
checker is caught.
"""

from domains.campaigns.models import (
    CAMPAIGN_STATUSES,
    CAMPAIGN_TEMPLATES,
    LEGAL_STATUS_TRANSITIONS,
    PART_STATES,
    is_legal_status_transition,
)

LEGAL = {
    ("planning", "running"),
    ("planning", "cancelled"),
    ("running", "finalizing"),
    ("running", "failed"),
    ("running", "cancelled"),
    ("finalizing", "done"),
    ("finalizing", "failed"),
}


def test_full_status_transition_matrix():
    for frm in CAMPAIGN_STATUSES:
        for to in CAMPAIGN_STATUSES:
            expected = (frm, to) in LEGAL
            assert is_legal_status_transition(frm, to) == expected, f"{frm} → {to}"


def test_terminal_statuses_have_no_exits():
    assert not LEGAL_STATUS_TRANSITIONS["done"]
    assert not LEGAL_STATUS_TRANSITIONS["failed"]
    assert not LEGAL_STATUS_TRANSITIONS["cancelled"]


def test_self_transitions_are_illegal():
    for status in CAMPAIGN_STATUSES:
        assert not is_legal_status_transition(status, status)


def test_vocabulary():
    assert CAMPAIGN_STATUSES == {
        "planning",
        "running",
        "finalizing",
        "done",
        "failed",
        "cancelled",
    }
    assert CAMPAIGN_TEMPLATES == {"full", "rotation", "focused"}
    assert PART_STATES == {"pending", "running", "done", "failed"}
