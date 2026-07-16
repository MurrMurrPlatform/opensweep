"""Pure retry-eligibility rules for quota-paused runs (PLATFORM_V2_DESIGN.md §8).

A paused run is retried:
  - immediately, when an unexhausted fallback provider exists (§8 fallback
    chain — no point waiting the reset window when another provider can run);
  - otherwise after the provider's reset window (OPENSWEEP_QUOTA_RETRY_MINUTES);
  - never beyond OPENSWEEP_QUOTA_MAX_RETRIES — then the run fails for real.

No I/O here: the resume beat task feeds in the recorded state and acts on the
returned decision.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum


class RetryAction(StrEnum):
    WAIT = "wait"
    RETRY = "retry"
    EXHAUSTED = "exhausted"


def decide_retry(
    *,
    now: datetime,
    detected_at: datetime | None,
    retry_count: int,
    retry_minutes: int,
    max_retries: int,
    fallback_available: bool,
) -> RetryAction:
    """Decide what to do with a quota-paused run.

    `detected_at is None` (corrupt/legacy pause record) counts as
    window-elapsed: better to retry than to strand the run forever.
    """
    if retry_count >= max_retries:
        return RetryAction.EXHAUSTED
    if fallback_available:
        return RetryAction.RETRY
    if detected_at is None:
        return RetryAction.RETRY
    if now - detected_at >= timedelta(minutes=retry_minutes):
        return RetryAction.RETRY
    return RetryAction.WAIT


def next_retry_at(
    *,
    detected_at: datetime,
    retry_minutes: int,
    fallback_available: bool,
) -> datetime:
    """Earliest moment a retry becomes eligible (UI: "retry N at ~HH:MM")."""
    if fallback_available:
        return detected_at
    return detected_at + timedelta(minutes=retry_minutes)
