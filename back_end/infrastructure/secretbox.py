"""Secrets encryption at rest — `enc:v1:<fernet-token>`.

Sealed values carry the `enc:v1:` prefix; anything without an `enc:` prefix
is legacy plaintext and loads forever (unseal is a passthrough for it).

Key handling:
  - OPENSWEEP_SECRETS_KEY — any string >= 16 chars; the Fernet key is derived as
    base64.urlsafe_b64encode(sha256(raw)). Losing it makes sealed secrets
    unrecoverable.
  - OPENSWEEP_SECRETS_KEY_FALLBACKS — comma-separated previous raw keys kept
    during rotation. Encryption always uses the primary; decryption tries
    primary then each fallback (MultiFernet).

Fail-closed: a sealed value that cannot be decrypted (missing/wrong key)
raises SecretBoxError — ciphertext is NEVER returned as if it were the
secret. Sealing without a key degrades to plaintext with a logged warning
(ERROR-level in production) so a fresh dev setup keeps working.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

logger = logging.getLogger(__name__)

PREFIX = "enc:v1:"
_MIN_KEY_LEN = 16


class SecretBoxError(RuntimeError):
    """A sealed secret could not be decrypted — fail closed."""


def _derive(raw: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()))


def _current_keys() -> tuple[str, tuple[str, ...]]:
    """Read settings lazily each call so tests can monkeypatch them."""
    from config import settings

    primary = (getattr(settings, "OPENSWEEP_SECRETS_KEY", "") or "").strip()
    fallbacks = tuple(
        k.strip()
        for k in (getattr(settings, "OPENSWEEP_SECRETS_KEY_FALLBACKS", "") or "").split(",")
        if k.strip()
    )
    return primary, fallbacks


# (primary, fallbacks) → (MultiFernet, primary Fernet). One entry: keys only
# change on config edits (or test monkeypatching — a changed tuple rebuilds).
_cache: dict[tuple[str, tuple[str, ...]], tuple[MultiFernet, Fernet]] = {}


def _reset_cache() -> None:
    _cache.clear()


def _boxes() -> tuple[MultiFernet, Fernet] | None:
    """The (MultiFernet, primary Fernet) pair, or None when unconfigured."""
    primary, fallbacks = _current_keys()
    if not primary:
        return None
    if len(primary) < _MIN_KEY_LEN:
        logger.warning(
            f"OPENSWEEP_SECRETS_KEY is shorter than {_MIN_KEY_LEN} chars — ignored; "
            "secrets encryption stays OFF"
        )
        return None
    key = (primary, fallbacks)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    primary_fernet = _derive(primary)
    fernets = [primary_fernet] + [_derive(f) for f in fallbacks if len(f) >= _MIN_KEY_LEN]
    entry = (MultiFernet(fernets), primary_fernet)
    _cache.clear()
    _cache[key] = entry
    return entry


def configured() -> bool:
    """True when a usable OPENSWEEP_SECRETS_KEY is set."""
    return _boxes() is not None


def is_sealed(value: str) -> bool:
    return (value or "").startswith(PREFIX)


def seal(plaintext: str) -> str:
    """Encrypt under the primary key. '' → ''; already-sealed → as-is;
    no key configured → plaintext back, with a logged warning (ERROR in
    production) — writes must not break an unconfigured deployment."""
    if not plaintext:
        return ""
    if is_sealed(plaintext):
        return plaintext
    boxes = _boxes()
    if boxes is None:
        from config import settings
        from infrastructure.production_guards import is_production

        msg = (
            "OPENSWEEP_SECRETS_KEY is not configured — secret stored in PLAINTEXT "
            "at rest. Set OPENSWEEP_SECRETS_KEY to enable encryption."
        )
        if is_production(getattr(settings, "ENVIRONMENT", "")):
            logger.error(msg)
        else:
            logger.warning(msg)
        return plaintext
    _, primary = boxes
    return PREFIX + primary.encrypt(plaintext.encode()).decode()


def unseal(value: str) -> str:
    """Decrypt a sealed value. No `enc:` prefix → returned as-is (legacy
    plaintext loads forever). Decrypt failure or missing key → SecretBoxError
    (FAIL CLOSED — ciphertext is never returned)."""
    value = value or ""
    if not value.startswith("enc:"):
        return value
    if not value.startswith(PREFIX):
        raise SecretBoxError(
            f"sealed secret has an unknown format version ({value.split(':', 2)[:2]}) — "
            "this OpenSweep build only understands enc:v1:. Upgrade the deployment."
        )
    boxes = _boxes()
    if boxes is None:
        raise SecretBoxError(
            "found an encrypted secret (enc:v1:) but OPENSWEEP_SECRETS_KEY is not "
            "configured — set OPENSWEEP_SECRETS_KEY to the key it was sealed with "
            "(and OPENSWEEP_SECRETS_KEY_FALLBACKS for any previous keys)."
        )
    multi, _ = boxes
    try:
        return multi.decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise SecretBoxError(
            "failed to decrypt a sealed secret: OPENSWEEP_SECRETS_KEY (and every "
            "OPENSWEEP_SECRETS_KEY_FALLBACKS entry) does not match the key it was "
            "sealed with. Add the old key to OPENSWEEP_SECRETS_KEY_FALLBACKS to "
            "recover, or re-enter the secret."
        ) from exc


def rotate(value: str) -> str:
    """Re-seal under the primary key iff the value is currently decryptable
    only by a fallback key. Plaintext input is sealed; primary-sealed input
    is returned unchanged (no churn)."""
    value = value or ""
    if not is_sealed(value):
        return seal(value)
    boxes = _boxes()
    if boxes is None:
        raise SecretBoxError(
            "cannot rotate a sealed secret without OPENSWEEP_SECRETS_KEY configured"
        )
    multi, primary = boxes
    token = value[len(PREFIX):].encode()
    try:
        primary.decrypt(token)
        return value  # already under the primary key
    except InvalidToken:
        pass
    try:
        return PREFIX + multi.rotate(token).decode()
    except InvalidToken as exc:
        raise SecretBoxError(
            "failed to rotate a sealed secret: no configured key "
            "(OPENSWEEP_SECRETS_KEY / OPENSWEEP_SECRETS_KEY_FALLBACKS) can decrypt it."
        ) from exc
