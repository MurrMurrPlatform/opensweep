"""Quota-exhaustion detection for CLI executors (PLATFORM_V2_DESIGN.md §8).

"Quota is a state, not a failure": when the provider CLI dies on a usage/rate
limit, the run is paused (`RunStatus.PAUSED_QUOTA`) and retried
after the provider's reset window instead of being marked failed.

This module is deliberately pure (no I/O, no models) so the detection matrix
is unit-testable. Adapters remain responsible for the one non-textual rule:
an agent SUCCESS (exit 0 with a completed tool flow — a parsed trailer /
envelope) is never quota, no matter what the transcript says.
"""

from __future__ import annotations

# Weak signals: only trusted when the process ALSO exited non-zero. Any of
# these can legitimately appear in prose (an agent investigating rate-limit
# handling, for instance), so on their own they prove nothing.
QUOTA_SIGNALS: tuple[str, ...] = (
    "usage limit",
    "rate limit",
    "quota",
    "429",
    "too many requests",
    "limit reached",
    "out of credits",
)

# Explicit quota messages: strong enough to pause on regardless of exit code.
# These are the literal phrasings the provider CLIs/APIs emit when a
# subscription or API budget is exhausted.
EXPLICIT_QUOTA_MESSAGES: tuple[str, ...] = (
    "usage limit reached",          # Claude CLI: "Claude AI usage limit reached|<ts>"
    "reached your usage limit",
    "hit your usage limit",         # Codex CLI phrasing
    "usage limit exceeded",
    "quota exceeded",
    "quota exhausted",
    "out of credits",
    "credit balance is too low",    # Anthropic API billing error
)

# Only the tail of the streams is inspected: quota errors terminate the
# process, so the message lands at the end. Matching the whole transcript
# would false-positive on runs that merely *discuss* limits early on.
_TAIL_CHARS = 4000


def _tail(text: str | None) -> str:
    return (text or "")[-_TAIL_CHARS:]


def detect_quota_exhaustion(
    exit_code: int | None,
    stdout: str | None,
    stderr: str | None,
) -> bool:
    """True when the output tail indicates provider quota/limit exhaustion.

    Conservative by design:
      - explicit quota message in the tail    → quota, with ANY exit code
      - weak signal in the tail               → quota, only with a NON-ZERO exit
      - clean exit without an explicit message → never quota
    """
    tail = f"{_tail(stdout)}\n{_tail(stderr)}".lower()
    if not tail.strip():
        return False
    if any(msg in tail for msg in EXPLICIT_QUOTA_MESSAGES):
        return True
    if exit_code is None or exit_code == 0:
        return False
    return any(signal in tail for signal in QUOTA_SIGNALS)
