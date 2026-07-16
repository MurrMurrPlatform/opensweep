"""GitHub App configuration — environment-provided deployment config.

The App is created OUTSIDE the platform by scripts/github-app-setup.sh
(GitHub only allows App creation through a logged-in browser, so the script
drives the manifest flow with one click and captures the credentials). The
platform just reads the result from the environment:

    GITHUB_APP_ID            numeric App id
    GITHUB_APP_SLUG          App slug — install URLs (github.com/apps/{slug})
    GITHUB_APP_PRIVATE_KEY   private key PEM, raw or base64-encoded (base64
                             survives .env/Coolify env transport unmangled)
    GITHUB_PRIVATE_KEY_PATH  alternative to GITHUB_APP_PRIVATE_KEY: path to a
                             PEM file (mounted-secret deployments)
    GITHUB_WEBHOOK_SECRET    webhook HMAC secret

Dev: written into .env by the setup script. Prod: terraform.tfvars →
coolify_envs_bulk (deployment/terraform). The App is "connected" when
GITHUB_APP_ID and a readable private key are both present.

Migrating a deployment that still holds credentials in the legacy
github_app.json (written by the removed in-app manifest flow): the file is no
longer read. Re-provision from GitHub → Settings → Developer settings → your
App (the App id and slug are on the page; generate a fresh private key, set a
new webhook secret) — installations and repo links are untouched by a re-key.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from pathlib import Path

from config import settings
from logging_config import logger

_GITHUB_WEB = "https://github.com"

_PEM_MARKER = "-----BEGIN"


@dataclass(frozen=True)
class GitHubAppConfig:
    app_id: str
    slug: str = ""
    pem: str = ""
    webhook_secret: str = ""
    html_url: str = ""


def secrets_dir() -> Path:
    """{ARTIFACT_STORE_ROOT}/../secrets — sits NEXT TO the artifact tree so
    artifact listings/exports can never sweep it up. Still used for the
    install-state file ledger (api/v1/github_app.py)."""
    root = Path(settings.ARTIFACT_STORE_ROOT)
    return root.parent / "secrets"


def _decode_private_key(raw: str) -> str:
    """Accept a raw PEM or its base64 encoding (the transport-safe form the
    setup script writes). Normalized to a trailing-newline PEM; "" when the
    value decodes to non-PEM junk."""
    value = raw.strip()
    if not value:
        return ""
    if value.startswith(_PEM_MARKER):
        return value + "\n"
    try:
        decoded = base64.b64decode(value, validate=True).decode().strip()
    except (binascii.Error, UnicodeDecodeError):
        decoded = ""
    if decoded.startswith(_PEM_MARKER):
        return decoded + "\n"
    logger.warning(
        "GITHUB_APP_PRIVATE_KEY is neither a PEM nor base64 of one — App disabled",
        extra={"tag": "github"},
    )
    return ""


def _read_private_key() -> str:
    """GITHUB_APP_PRIVATE_KEY (inline) wins over GITHUB_PRIVATE_KEY_PATH."""
    inline = (settings.GITHUB_APP_PRIVATE_KEY or "").strip()
    if inline:
        return _decode_private_key(inline)
    key_path = (settings.GITHUB_PRIVATE_KEY_PATH or "").strip()
    if not key_path:
        return ""
    try:
        return Path(key_path).read_text()
    except OSError as exc:
        logger.warning(
            f"GITHUB_PRIVATE_KEY_PATH set but unreadable ({exc}) — App disabled",
            extra={"tag": "github"},
        )
        return ""


# (env fingerprint) → config. Env is static per process, but tests monkeypatch
# settings, so the fingerprint (not process lifetime) keys the cache.
_cache: dict | None = None


def _invalidate_cache() -> None:
    global _cache
    _cache = None


def get_github_app() -> GitHubAppConfig | None:
    """The configured GitHub App, or None when no App is configured."""
    global _cache

    key = (
        settings.GITHUB_APP_ID,
        settings.GITHUB_APP_SLUG,
        settings.GITHUB_APP_PRIVATE_KEY,
        settings.GITHUB_PRIVATE_KEY_PATH,
        settings.GITHUB_WEBHOOK_SECRET,
    )
    if _cache is not None and _cache.get("key") == key:
        return _cache.get("config")

    app_id = (settings.GITHUB_APP_ID or "").strip()
    pem = _read_private_key() if app_id else ""
    if not app_id or not pem:
        config = None
    else:
        slug = (settings.GITHUB_APP_SLUG or "").strip()
        config = GitHubAppConfig(
            app_id=app_id,
            slug=slug,
            pem=pem,
            webhook_secret=settings.GITHUB_WEBHOOK_SECRET or "",
            html_url=f"{_GITHUB_WEB}/apps/{slug}" if slug else "",
        )
    _cache = {"key": key, "config": config}
    return config
