"""Quota-exhaustion detection matrix (pure — domains/executors/quota.py)."""

import pytest

from domains.executors.quota import detect_quota_exhaustion


class TestWeakSignalsRequireNonZeroExit:
    @pytest.mark.parametrize(
        "signal",
        [
            "usage limit",
            "rate limit",
            "quota",
            "429",
            "too many requests",
            "limit reached",
            "out of credits",
        ],
    )
    def test_signal_with_nonzero_exit_is_quota(self, signal):
        assert detect_quota_exhaustion(1, f"error: {signal} hit", "") is True

    @pytest.mark.parametrize("signal", ["rate limit", "quota", "429", "too many requests"])
    def test_weak_signal_with_zero_exit_is_not_quota(self, signal):
        assert detect_quota_exhaustion(0, f"the code handles {signal} responses", "") is False

    def test_weak_signal_with_none_exit_is_not_quota(self):
        assert detect_quota_exhaustion(None, "got a 429 somewhere", "") is False

    def test_signal_in_stderr_counts(self):
        assert detect_quota_exhaustion(2, "", "HTTP 429 Too Many Requests") is True

    def test_case_insensitive(self):
        assert detect_quota_exhaustion(1, "RATE LIMIT EXCEEDED", "") is True


class TestExplicitMessagesAnyExit:
    @pytest.mark.parametrize(
        "message",
        [
            "Claude AI usage limit reached|1720000000",
            "You've reached your usage limit.",
            "You've hit your usage limit — upgrade or wait.",
            "usage limit exceeded",
            "quota exceeded for this billing period",
            "quota exhausted",
            "you are out of credits",
            "Your credit balance is too low to access the API.",
        ],
    )
    @pytest.mark.parametrize("exit_code", [0, 1, None])
    def test_explicit_message_is_quota_regardless_of_exit(self, message, exit_code):
        assert detect_quota_exhaustion(exit_code, message, "") is True

    def test_explicit_message_in_stderr_with_zero_exit(self):
        assert detect_quota_exhaustion(0, "partial output...", "usage limit reached") is True


class TestConservatism:
    def test_empty_output_is_never_quota(self):
        assert detect_quota_exhaustion(1, "", "") is False
        assert detect_quota_exhaustion(0, "", "") is False
        assert detect_quota_exhaustion(None, None, None) is False

    def test_nonzero_exit_without_signal_is_not_quota(self):
        assert detect_quota_exhaustion(1, "Traceback: ValueError in foo.py", "boom") is False

    def test_clean_success_prose_mentioning_quota_is_not_quota(self):
        transcript = (
            "Investigated the API client. Filed a finding about missing "
            "retry handling for quota errors. complete_run called."
        )
        assert detect_quota_exhaustion(0, transcript, "") is False

    def test_signal_outside_tail_is_ignored(self):
        # Signal buried early in a long transcript, well before the 4000-char
        # tail: the process did not die on it.
        early = "the server returned 429 too many requests once\n"
        padding = "line of ordinary output\n" * 400  # ≈ 9600 chars of padding
        assert detect_quota_exhaustion(1, early + padding, "") is False

    def test_signal_inside_tail_is_seen(self):
        padding = "line of ordinary output\n" * 400
        late = "\nerror: rate limit exceeded"
        assert detect_quota_exhaustion(1, padding + late, "") is True

    def test_explicit_message_outside_tail_is_ignored(self):
        early = "Claude AI usage limit reached|123\n"
        padding = "line of ordinary output\n" * 400
        assert detect_quota_exhaustion(0, early + padding, "") is False
