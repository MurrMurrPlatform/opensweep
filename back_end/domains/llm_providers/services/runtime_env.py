"""Compose the env / CWD a worker needs to invoke an LLMProvider's CLI.

Reads a stored `credential_secret` off the LLMProvider node and produces:
- `env_vars`: dict to merge into subprocess env
- `extra_files`: list of (path, content, mode) tuples to write before invocation
  (eg. for Codex which needs auth.json on disk).

Falls back to environment variables (`CLAUDE_CODE_OAUTH_TOKEN`, `<api_key_env>`)
when no UI-stored secret is present, so .env-based setups keep working.
"""

import os
import shutil
import tempfile
from dataclasses import dataclass, field

from domains.llm_providers.models import LLMProvider
from domains.llm_providers.schemas import LLMProviderKind
from domains.llm_providers.services.credentials import provider_secret

_CODEX_HOME_PREFIX = "opensweep-codex-"


@dataclass
class ProviderRuntime:
    env_vars: dict[str, str] = field(default_factory=dict)
    extra_files: list[tuple[str, str, int]] = field(default_factory=list)
    # If set, the worker should run with HOME pointing here (so the CLI looks for
    # its dotfiles under this dir). Used by codex when we write a private auth.json.
    home_override: str | None = None

    def cleanup(self) -> None:
        """Delete the worker-private home dir (it holds `auth.json` — a full
        OAuth blob) once the invocation is done (audit #21).

        Guarded to `opensweep-codex-*` dirs directly under the system temp dir so
        a misconfigured `home_override` can never delete anything else.
        Idempotent and never raises — credential hygiene must not fail a run.
        """
        home = self.home_override
        self.home_override = None
        if not home:
            return
        normalized = os.path.normpath(home)
        if (
            os.path.dirname(normalized) != tempfile.gettempdir()
            or not os.path.basename(normalized).startswith(_CODEX_HOME_PREFIX)
        ):
            return
        shutil.rmtree(normalized, ignore_errors=True)

    def __enter__(self) -> "ProviderRuntime":
        return self

    def __exit__(self, *exc: object) -> None:
        self.cleanup()


def _codex_home(provider: LLMProvider) -> str:
    """Deterministic worker-private CODEX_HOME for this provider.

    One dir per provider, reused (auth.json overwritten) across invocations —
    the previous mkdtemp-per-invocation leaked an OAuth-blob-bearing dir on
    every codex turn and nothing ever deleted them (audit #21).
    """
    uid = "".join(
        c for c in (getattr(provider, "uid", "") or "") if c.isalnum() or c in "-_"
    ) or "default"
    return os.path.join(tempfile.gettempdir(), f"{_CODEX_HOME_PREFIX}{uid}")


def build_runtime(provider: LLMProvider) -> ProviderRuntime:
    rt = ProviderRuntime()
    secret = provider_secret(provider)
    kind = provider.kind

    if kind == LLMProviderKind.CLAUDE_SUBSCRIPTION.value:
        if secret:
            rt.env_vars["CLAUDE_CODE_OAUTH_TOKEN"] = secret
        elif os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            rt.env_vars["CLAUDE_CODE_OAUTH_TOKEN"] = os.environ["CLAUDE_CODE_OAUTH_TOKEN"]
        return rt

    if kind == LLMProviderKind.CODEX_SUBSCRIPTION.value:
        if secret:
            # Write the auth.json blob to a worker-private CODEX_HOME so we don't
            # touch the host-bind-mounted ~/.codex.
            home = _codex_home(provider)
            os.makedirs(f"{home}/.codex", mode=0o700, exist_ok=True)
            rt.extra_files.append((f"{home}/.codex/auth.json", secret, 0o600))
            rt.home_override = home
        # else: fall through and use whatever's in the bind-mounted /root/.codex
        return rt

    if kind in (LLMProviderKind.CLAUDE_API.value, LLMProviderKind.OPENAI_API.value):
        env_name = provider.api_key_env or (
            "ANTHROPIC_API_KEY" if kind == LLMProviderKind.CLAUDE_API.value else "OPENAI_API_KEY"
        )
        if secret:
            rt.env_vars[env_name] = secret
        elif os.environ.get(env_name):
            rt.env_vars[env_name] = os.environ[env_name]
        return rt

    # MLX / LMStudio / Ollama / custom — no credential plumbing needed.
    return rt
