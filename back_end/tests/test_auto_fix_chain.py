"""Review → verify → fix chain contracts (§A/§C).

The chain functions are DB-bound; what we pin here purely is the guard
set each link enforces and the model-level state vocabulary they rely on.
Loop bounding itself (fix_rounds burned pre-dispatch, 409 at max) is
covered by test_fix_rounds_surface.py / test_write_gate.py.
"""

import inspect

from domains.delivery.models import (
    NON_BLOCKING_STATES,
    RESOLUTION_STATES,
    VERDICT_VERIFICATION_STATUSES,
    VERIFICATION_RESULTS,
)
from domains.delivery.services.fix_run_service import maybe_auto_fix_for_pr
from domains.runs.services.playbooks import _continue_review_chain


def test_state_vocabulary_covers_the_skeptic_pass():
    assert "refuted" in RESOLUTION_STATES
    assert "refuted" in NON_BLOCKING_STATES
    assert VERIFICATION_RESULTS == {"confirmed", "refuted", "needs-human"}
    assert VERDICT_VERIFICATION_STATUSES == {"", "pending", "adjusted", "superseded", "failed"}


def test_auto_fix_skips_pending_verification_and_stale_verdicts():
    src = inspect.getsource(maybe_auto_fix_for_pr)
    # The skeptic pass owns the chain until it lands.
    assert '== "pending"' in src
    # Never chain off a verdict at a different sha than head.
    assert "verdict.sha" in src and "head_sha" in src
    # Auto-fix remains a per-repo opt-in.
    assert 'stage_auto(pr.repository_uid, "fix")' in src


def test_review_chain_dispatches_verification_before_fix():
    src = inspect.getsource(_continue_review_chain)
    assert "trigger_verification_run" in src
    assert "maybe_auto_fix_for_pr" in src
    # Verification dispatch failure fails OPEN (marks the verdict failed) so
    # a pending verdict can never wedge the fix chain forever.
    assert 'verification_status = "failed"' in src
