"""Verification-run intent contract (§A) — the skeptic prompt must pin the
sha, mandate a per-finding report, and forbid verdicts/writes."""

from domains.delivery.models import PullRequest, Verdict
from domains.delivery.services.verification_run_service import (
    adjusted_verdict_outcome,
    build_verification_intent,
)

HEAD = "c0ffee1234deadbeefc0ffee1234deadbeefc0ff"


def _pr() -> PullRequest:
    return PullRequest(
        uid="pr1",
        repository_uid="repo1",
        github_number=72,
        pr_key="repo1:72",
        title="Event messaging",
        head_sha=HEAD,
        head_ref="feat/event-messaging",
        base_ref="main",
    )


def _verdict() -> Verdict:
    return Verdict(
        uid="v1",
        pull_request_uid="pr1",
        repository_uid="repo1",
        sha=HEAD,
        result="request_changes",
        new_blocking_findings=2,
        finding_uids=["f1", "f2"],
    )


def _findings() -> list[dict]:
    return [
        {
            "finding_uid": "f1",
            "resolution_uid": "res1",
            "title": "Race in cache invalidation",
            "severity": "high",
            "evidence": {"note": "rollback path skips invalidate"},
            "affected_paths": ["src/cache.py"],
        },
        {
            "finding_uid": "f2",
            "resolution_uid": "res2",
            "title": "Missing authz check",
            "severity": "critical",
            "evidence": {},
            "affected_paths": [],
        },
    ]


def test_intent_pins_the_verdict_sha_and_falls_back_to_needs_human():
    intent = build_verification_intent(_pr(), _verdict(), _findings())
    assert f"`{HEAD[:12]}`" in intent
    assert "needs-human" in intent
    assert "never judge a different commit" in intent.lower()


def test_intent_mandates_one_report_per_finding_and_silence_confirms():
    intent = build_verification_intent(_pr(), _verdict(), _findings())
    assert "opensweep_platform_submit_finding_verification" in intent
    assert "`f1`" in intent and "`f2`" in intent
    assert "silence never dismisses a finding" in intent.lower()


def test_intent_takes_the_refute_stance_with_evidence_bar():
    intent = build_verification_intent(_pr(), _verdict(), _findings())
    assert "REFUTE" in intent
    assert "file:line" in intent
    assert "Never guess" in intent


def test_intent_is_read_only_and_submits_no_verdict():
    intent = build_verification_intent(_pr(), _verdict(), _findings())
    assert "Do not modify any file" in intent
    assert "Do not submit a verdict" in intent


def test_intent_appends_verify_guidance_after_the_contract():
    base = build_verification_intent(_pr(), _verdict(), _findings())
    with_guidance = build_verification_intent(
        _pr(), _verdict(), _findings(), guidance="Check sibling call sites."
    )
    assert base in with_guidance
    assert "Check sibling call sites." in with_guidance


# ── Adjusted-verdict math (pure) ─────────────────────────────────────────────


def test_zero_confirmed_blocking_approves():
    result, blocking = adjusted_verdict_outcome([], {"default": "high"})
    assert (result, blocking) == ("approve", 0)
    # Survivors below the threshold don't block either.
    result, blocking = adjusted_verdict_outcome(
        [{"severity": "low", "tags": []}], {"default": "high"}
    )
    assert (result, blocking) == ("approve", 0)


def test_confirmed_blocking_findings_keep_request_changes():
    confirmed = [
        {"severity": "high", "tags": []},
        {"severity": "medium", "tags": ["security"]},  # per-tag threshold hits
        {"severity": "low", "tags": []},
    ]
    policy = {"default": "high", "per_tag": {"security": "medium"}}
    result, blocking = adjusted_verdict_outcome(confirmed, policy)
    assert (result, blocking) == ("request_changes", 2)
