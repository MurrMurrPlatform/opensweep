"""Stable dedupe-key generation for Findings.

A Finding's dedupe_key collapses repeat reports of the same issue across
multiple audit Runs. The key is derived from:
  repository_uid + normalised title + top affected path

Title normalisation strips numbers, file:line excerpts, and whitespace so
two reports of the same issue produce the same key even if the LLM
rephrased.
"""

import difflib
import hashlib
import re

_NORMALISE_RE = re.compile(r"[\W_0-9]+")


def _normalise_title(title: str) -> str:
    t = (title or "").lower()
    t = _NORMALISE_RE.sub(" ", t)
    return " ".join(t.split())[:120]


def titles_similar(a: str, b: str, threshold: float = 0.75) -> bool:
    """True when two finding titles read as the same issue after
    normalisation (case/numbers/punctuation stripped). Used by the
    create_finding similarity fallback when the exact dedupe_key misses —
    e.g. an LLM rephrasing "SQL injection in the /users endpoint" as
    "Possible SQL injection in the users endpoint"."""
    na = _normalise_title(a)
    nb = _normalise_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= threshold


def build_dedupe_key(
    *,
    repository_uid: str,
    title: str,
    top_path: str,
) -> str:
    raw = "|".join(
        [
            (repository_uid or ""),
            _normalise_title(title),
            (top_path or "").lower(),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]
