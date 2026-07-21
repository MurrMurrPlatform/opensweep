"""Codex `~/.codex/auth.json` document helpers — pure, parse-only.

Approach A (see the codex token-refresh design doc): codex owns the OAuth
refresh. OpenSweep never calls the token endpoint; it seeds codex's auth.json,
lets codex refresh in place under an exclusive per-subscription lock, and
persists whatever codex leaves behind **verbatim** — so the stored document is
inherently lossless (unknown / forward-compatible fields survive untouched).

These helpers only parse, validate, and compare that document, and recognise
codex's re-authentication failure text. No I/O, no token minting.
"""

from __future__ import annotations

import json

# Substrings codex emits (stdout/stderr) when the refresh token is permanently
# dead — matched case-insensitively. Kept deliberately broad; a false positive
# only sets `needs_reauth`, which a successful re-paste clears.
_REAUTH_SIGNATURES = (
    "access token could not be refreshed",
    "please log out and sign in again",
    "run `codex login`",
    "run codex login",
    "not logged in",
    "re-authenticate",
)

# Fields codex rotates on refresh; a change in any means the durable copy is stale.
_ROTATING_TOKEN_FIELDS = ("access_token", "refresh_token", "id_token")


def parse_document(text: str) -> dict | None:
    """The parsed auth.json object, or None if it is not a JSON object."""
    try:
        doc = json.loads(text)
    except (ValueError, TypeError):
        return None
    return doc if isinstance(doc, dict) else None


def _tokens(doc: dict) -> dict:
    tokens = doc.get("tokens")
    return tokens if isinstance(tokens, dict) else {}


def is_valid(text: str) -> bool:
    """True for a usable managed-ChatGPT auth.json: parses and carries a
    non-empty access token. Guards against persisting a partially-written or
    truncated file (e.g. codex killed mid-rotation)."""
    doc = parse_document(text)
    if doc is None:
        return False
    return bool(str(_tokens(doc).get("access_token") or "").strip())


def account_id(text: str) -> str:
    doc = parse_document(text)
    if doc is None:
        return ""
    return str(_tokens(doc).get("account_id") or "")


def same_account(seed_text: str, result_text: str) -> bool:
    """True when the result belongs to the same ChatGPT account as the seed.

    Guards write-back against a swapped identity. If the seed carries no
    account_id (older codex versions), there is nothing to compare, so we do
    not block."""
    seed = account_id(seed_text)
    if not seed:
        return True
    return seed == account_id(result_text)


def changed(seed_text: str, result_text: str) -> bool:
    """True when codex rotated the credential relative to the seeded copy.

    Compares the rotating token fields plus `last_refresh` (not raw bytes) so
    incidental whitespace/formatting never triggers a needless revision bump."""
    seed = parse_document(seed_text) or {}
    result = parse_document(result_text) or {}
    seed_tokens, result_tokens = _tokens(seed), _tokens(result)
    if any(seed_tokens.get(k) != result_tokens.get(k) for k in _ROTATING_TOKEN_FIELDS):
        return True
    return seed.get("last_refresh") != result.get("last_refresh")


def looks_like_reauth(text: str) -> bool:
    """True when codex's output indicates the refresh token is permanently dead."""
    low = (text or "").lower()
    return any(sig in low for sig in _REAUTH_SIGNATURES)


# Write-back decision, factored out so it is unit-testable without a database.
PERSIST = "persist"          # codex rotated a valid credential — CAS-persist it
NOOP = "noop"                # nothing new to store
UNCERTAIN = "uncertain"      # a changed-but-invalid file — health is unknown
REJECT_ACCOUNT = "reject_account"  # identity mismatch — never persist


def decide_write_back(seed_text: str, result_text: str | None) -> str:
    """Classify what to do with the on-disk auth.json after a turn.

    `result_text` is None when codex left no readable file (bind-mount, or it
    never ran)."""
    if result_text is None:
        return NOOP
    if not is_valid(result_text):
        # A non-empty file that differs from the seed but does not parse to a
        # usable credential means codex may have been mid-rotation when the
        # turn was interrupted — the durable token's health is now unknown.
        if result_text.strip() and result_text != seed_text:
            return UNCERTAIN
        return NOOP
    if not changed(seed_text, result_text):
        return NOOP
    if not same_account(seed_text, result_text):
        return REJECT_ACCOUNT
    return PERSIST
