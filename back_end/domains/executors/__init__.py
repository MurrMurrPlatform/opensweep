"""Executor adapters.

PLATFORM.md §Executors: the platform itself does not do agentic code
work. It dispatches Runs to one of:

- internal_llm   (Phase 6)
- claude_code    (Phase 5)
- codex          (tracking-only CLI adapter)
- opencode       (tracking-only CLI adapter)
- manual         (Phase 4 — humans posting results via the HTTP transport)
"""
