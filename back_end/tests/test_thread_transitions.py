"""Thread phase state machine (unified dev flow Phase 1).

Pure tests, mirroring tests/test_ticket_transitions.py: the full legality
matrix spelled out pairwise so a regression in either the dict or the
checker is caught.
"""

from domains.threads.models import (
    LEGAL_PHASE_TRANSITIONS,
    PLAN_STATES,
    THREAD_PHASES,
    is_legal_phase_transition,
)

LEGAL = {
    ("refining", "implementing"),
    ("implementing", "in_review"),
    ("in_review", "done"),
    # any non-terminal phase can be abandoned
    ("refining", "abandoned"),
    ("implementing", "abandoned"),
    ("in_review", "abandoned"),
}


def test_full_phase_transition_matrix():
    for frm in THREAD_PHASES:
        for to in THREAD_PHASES:
            expected = (frm, to) in LEGAL
            assert is_legal_phase_transition(frm, to) == expected, f"{frm} → {to}"


def test_terminal_phases_have_no_exits():
    assert not LEGAL_PHASE_TRANSITIONS["done"]
    assert not LEGAL_PHASE_TRANSITIONS["abandoned"]


def test_self_transitions_are_illegal():
    for phase in THREAD_PHASES:
        assert not is_legal_phase_transition(phase, phase)


def test_vocabulary():
    assert THREAD_PHASES == {"refining", "implementing", "in_review", "done", "abandoned"}
    assert PLAN_STATES == {"none", "drafted", "approved"}
