"""Ticket state machine + role ordering (PLATFORM_V2_DESIGN.md §2, §15 Phase 2).

Pure tests: the transition legality matrix, Gate-1 role gating primitives,
and the priority ordering used by the board listing.
"""

import pytest
from fastapi import HTTPException

from api.dependencies import require_role
from domains.tickets.models import TICKET_STATUSES
from domains.tickets.services.ticket_service import (
    GATE_1,
    LEGAL_TRANSITIONS,
    is_legal_transition,
    priority_rank,
)
from domains.users.schemas import ROLE_ORDER, UserDTO, role_at_least

# ── Transition matrix ────────────────────────────────────────────────────────

# The full legality matrix, spelled out pairwise so a regression in either the
# dict or the checker is caught.
LEGAL = {
    ("backlog", "todo"),  # GATE 1
    ("todo", "backlog"),
    ("todo", "in-progress"),
    ("in-progress", "in-review"),
    ("in-progress", "todo"),
    ("in-progress", "backlog"),  # de-prioritize
    ("in-review", "in-progress"),
    ("in-review", "done"),
    ("in-review", "backlog"),  # de-prioritize
}


def test_full_transition_matrix():
    for frm in TICKET_STATUSES:
        for to in TICKET_STATUSES:
            expected = (frm, to) in LEGAL
            assert is_legal_transition(frm, to) == expected, f"{frm} → {to}"


def test_done_is_terminal():
    assert not LEGAL_TRANSITIONS["done"]
    for to in TICKET_STATUSES:
        assert not is_legal_transition("done", to)


def test_any_to_backlog_except_done_and_self():
    for frm in TICKET_STATUSES - {"done", "backlog"}:
        assert is_legal_transition(frm, "backlog"), f"{frm} → backlog must be legal"
    assert not is_legal_transition("done", "backlog")


def test_self_transitions_are_illegal():
    for status in TICKET_STATUSES:
        assert not is_legal_transition(status, status)


def test_unknown_statuses_are_illegal():
    assert not is_legal_transition("nope", "todo")
    assert not is_legal_transition("backlog", "nope")


def test_gate_1_is_backlog_to_todo():
    assert GATE_1 == ("backlog", "todo")
    assert is_legal_transition(*GATE_1)


def test_matrix_only_names_known_statuses():
    for frm, targets in LEGAL_TRANSITIONS.items():
        assert frm in TICKET_STATUSES
        assert targets <= TICKET_STATUSES


# ── Role ordering (Gate-1 gating primitive) ──────────────────────────────────


def test_role_order_is_viewer_maintainer_admin():
    assert ROLE_ORDER["viewer"] < ROLE_ORDER["maintainer"] < ROLE_ORDER["admin"]


def test_role_at_least():
    assert role_at_least("admin", "maintainer")
    assert role_at_least("maintainer", "maintainer")
    assert role_at_least("admin", "viewer")
    assert not role_at_least("viewer", "maintainer")
    assert not role_at_least("maintainer", "admin")
    # Unknown roles never qualify; unknown minimums are unsatisfiable.
    assert not role_at_least("intern", "viewer")
    assert not role_at_least("admin", "superadmin")


def _user(role: str) -> UserDTO:
    return UserDTO(uid="u1", email="u@example.dev", display_name="U", role=role, org_uid="local-org")


def test_require_role_allows_at_or_above_minimum():
    dep = require_role("maintainer")
    assert dep(user=_user("maintainer")).uid == "u1"
    assert dep(user=_user("admin")).uid == "u1"


def test_require_role_rejects_below_minimum_with_403():
    dep = require_role("maintainer")
    with pytest.raises(HTTPException) as exc:
        dep(user=_user("viewer"))
    assert exc.value.status_code == 403


def test_local_bootstrap_user_is_admin():
    from domains.users.services.local_user import get_local_user

    assert get_local_user().role == "admin"


# ── Board ordering ───────────────────────────────────────────────────────────


def test_priority_rank_orders_urgent_first():
    assert (
        priority_rank("urgent")
        > priority_rank("high")
        > priority_rank("medium")
        > priority_rank("low")
    )


def test_priority_rank_unknown_defaults_to_medium():
    assert priority_rank("") == priority_rank("medium")
    assert priority_rank("whenever") == priority_rank("medium")
