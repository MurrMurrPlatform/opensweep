"""Reasoning level → provider-specific knobs.

One pure mapping so every adapter agrees on what "low/medium/high" means per
provider kind (domains/llm_providers/schemas.LLMProviderKind values):

- claude_subscription: the Claude Code CLI reads MAX_THINKING_TOKENS from the
  environment. "low" disables thinking ("0"); "medium" omits the key (the CLI
  default IS medium); "high" raises the budget to 31999.
- codex_subscription: `-c model_reasoning_effort=<level>` argv override —
  passed explicitly for every level (codex's own default may drift).
- claude_api: the Messages-API thinking block (budget_tokens per level; "low"
  means disabled).
- openai_api: OpenAI-compatible `reasoning_effort` request field.
- mlx / lmstudio / ollama: local OpenAI-compatible servers — the executor's
  `suppress_thinking` override ("low" suppresses chain-of-thought, else the
  model thinks freely).

Unknown kinds (and level == "") get no knobs at all: {}.
"""

from __future__ import annotations

_LEVELS = {"low", "medium", "high"}

# Anthropic Messages-API thinking budgets per level ("low" disables instead).
_ANTHROPIC_BUDGET_TOKENS = {"medium": 8192, "high": 24576}

# Claude Code CLI env budgets ("medium" omits the key — the CLI default).
_CLAUDE_CLI_THINKING_TOKENS = {"low": "0", "high": "31999"}

_LOCAL_KINDS = {"mlx", "lmstudio", "ollama"}


def reasoning_args(level: str, provider_kind: str) -> dict:
    """Provider knobs for a reasoning level, keyed by transport:

    {"env": {...}}         — subprocess environment additions (claude CLI)
    {"cli_config": [...]}  — extra argv tokens (codex CLI)
    {"api": {...}}         — request-body overrides (HTTP kinds)

    Empty dict when the level is unset/unknown or the kind takes no knob.
    """
    lvl = (level or "").strip().lower()
    kind = (provider_kind or "").strip()
    if lvl not in _LEVELS:
        return {}

    if kind == "claude_subscription":
        tokens = _CLAUDE_CLI_THINKING_TOKENS.get(lvl)
        return {"env": {"MAX_THINKING_TOKENS": tokens}} if tokens is not None else {}

    if kind == "codex_subscription":
        return {"cli_config": ["-c", f"model_reasoning_effort={lvl}"]}

    if kind == "claude_api":
        if lvl == "low":
            return {"api": {"thinking": {"type": "disabled"}}}
        return {
            "api": {
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": _ANTHROPIC_BUDGET_TOKENS[lvl],
                }
            }
        }

    if kind == "openai_api":
        return {"api": {"reasoning_effort": lvl}}

    if kind in _LOCAL_KINDS:
        return {"api": {"suppress_thinking": lvl == "low"}}

    return {}
