"""Waive suppression (§4: waive once, suppress forever) — pure guards.

Two halves of the hole:
  1. Binding a wont-fix Finding to a NEW PR must create the resolution
     already waived, not resurrect it as an open blocker.
  2. Waiving must flip the Finding to wont-fix from ANY non-terminal status,
     not just OPEN — otherwise an acknowledged finding keeps re-appearing.
"""

from domains.delivery.services.resolution_service import (
    TERMINAL_FINDING_STATUSES,
    finding_flips_to_wont_fix,
    initial_resolution_state_for_finding,
)
from domains.findings.schemas import FindingStatus

# ── Half 1: resolutions born from wont-fix findings arrive waived ────────────


def test_wont_fix_finding_binds_as_waived_with_stored_reason():
    state, reason = initial_resolution_state_for_finding(
        FindingStatus.WONT_FIX.value, {"waive_reason": "false positive on generated code"}
    )
    assert state == "waived"
    assert reason == "false positive on generated code"


def test_wont_fix_finding_without_stored_reason_gets_default():
    state, reason = initial_resolution_state_for_finding(FindingStatus.WONT_FIX.value, {})
    assert state == "waived"
    assert reason == "finding is wont-fix"
    # None evidence is tolerated too.
    state2, reason2 = initial_resolution_state_for_finding(FindingStatus.WONT_FIX.value, None)
    assert (state2, reason2) == ("waived", "finding is wont-fix")


def test_open_finding_binds_as_open():
    for status in ("open", "acknowledged", "fixed", ""):
        state, reason = initial_resolution_state_for_finding(status, {})
        assert state == "open"
        assert reason == ""


# ── Half 2: waive flips the Finding from any non-terminal status ─────────────


def test_waive_flips_open_and_acknowledged():
    assert finding_flips_to_wont_fix(FindingStatus.OPEN.value)
    assert finding_flips_to_wont_fix(FindingStatus.ACKNOWLEDGED.value)
    # Re-waiving an already wont-fix finding is an idempotent refresh.
    assert finding_flips_to_wont_fix(FindingStatus.WONT_FIX.value)
    # Missing/blank status defaults to open behavior.
    assert finding_flips_to_wont_fix("")


def test_waive_never_overwrites_terminal_statuses():
    for status in ("accepted", "superseded", "dismissed", "fixed"):
        assert not finding_flips_to_wont_fix(status)


def test_terminal_set_matches_spec():
    assert TERMINAL_FINDING_STATUSES == {"accepted", "superseded", "dismissed", "fixed"}
