"""Retry eligibility for quota-paused runs (pure — quota_retry.decide_retry)."""

from datetime import UTC, datetime, timedelta

from domains.runs.services.quota_retry import (
    RetryAction,
    decide_retry,
    next_retry_at,
)

NOW = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


def decide(**overrides):
    kwargs = dict(
        now=NOW,
        detected_at=NOW - timedelta(minutes=45),
        retry_count=0,
        retry_minutes=30,
        max_retries=6,
        fallback_available=False,
    )
    kwargs.update(overrides)
    return decide_retry(**kwargs)


class TestWindow:
    def test_window_elapsed_retries(self):
        assert decide(detected_at=NOW - timedelta(minutes=30)) == RetryAction.RETRY

    def test_window_not_elapsed_waits(self):
        assert decide(detected_at=NOW - timedelta(minutes=29)) == RetryAction.WAIT

    def test_just_paused_waits(self):
        assert decide(detected_at=NOW) == RetryAction.WAIT

    def test_missing_detected_at_retries(self):
        # Corrupt/legacy pause record: never strand the run forever.
        assert decide(detected_at=None) == RetryAction.RETRY


class TestFallbackShortCircuit:
    def test_fallback_available_retries_immediately(self):
        assert decide(detected_at=NOW, fallback_available=True) == RetryAction.RETRY

    def test_fallback_does_not_override_max_retries(self):
        assert (
            decide(retry_count=6, fallback_available=True) == RetryAction.EXHAUSTED
        )


class TestMaxRetries:
    def test_at_max_retries_is_exhausted(self):
        assert decide(retry_count=6) == RetryAction.EXHAUSTED

    def test_beyond_max_retries_is_exhausted(self):
        assert decide(retry_count=7) == RetryAction.EXHAUSTED

    def test_below_max_retries_still_eligible(self):
        assert decide(retry_count=5) == RetryAction.RETRY

    def test_exhausted_even_when_window_not_elapsed(self):
        assert decide(retry_count=6, detected_at=NOW) == RetryAction.EXHAUSTED


class TestNextRetryAt:
    def test_without_fallback_adds_reset_window(self):
        detected = NOW
        assert next_retry_at(
            detected_at=detected, retry_minutes=30, fallback_available=False
        ) == detected + timedelta(minutes=30)

    def test_with_fallback_is_immediate(self):
        detected = NOW
        assert (
            next_retry_at(detected_at=detected, retry_minutes=30, fallback_available=True)
            == detected
        )
