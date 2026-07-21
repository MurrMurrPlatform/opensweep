"""Layer resolution + intent composition for agent runs.

The composed prompt (the cake — org-agent-overlays spec §Composition,
carried over unchanged into the Agent model):

    OPENSWEEP_FRAMING_HEADER      code; always included
    <platform instructions>       the system Agent's prompt for the key
                                  — or the org override body when mode=replace
    ## Organization guidance      org override body when mode=append
    ## <Stage> guidance           per-repo workflow-config prompt (unchanged)
    # Scope / existing state      the run's structural contract + scope
    LOOK_BEFORE_WRITE_FOOTER      code; unconditional (chat has none)

`build_intent` (runs/_intent_helpers.py) does the pure assembly; this
module resolves the async layers — system agent body, org override, repo
stage guidance — degrading ONE layer at a time with a log line. A dangling
or disabled row never fails a run: missing override ⇒ platform body as-is;
missing/disabled system row ⇒ the in-code fallback instructions.
"""

from __future__ import annotations

from dataclasses import dataclass

from domains.agents.schemas import OverlayMode
from logging_config import logger

# Agent key → workflow stage whose per-repo prompt stacks as repo guidance.
# refine and chat have no workflow stage; deep-scan/generate-docs callers
# pass their stage (or pre-resolved guidance) explicitly, exactly as they
# did against the old overlay composition.
_KEY_STAGE = {
    "ask": "ask",
    "review": "review",
    "fix": "fix",
    "implement": "implement",
    "verify": "verify",
    "document": "document",
}

# Representative scope stub for the preview endpoint — the real run
# substitutes its own scope/target/existing-state sections here.
PREVIEW_SCOPE_STUB = (
    "(preview) Representative scope: a real run replaces this section with its "
    "concrete target — e.g. the pull request under review, the findings to fix, "
    "or the ticket's acceptance criteria — plus any repository state listings."
)


@dataclass(frozen=True)
class ComposedIntent:
    text: str
    agent_uid: str = ""
    agent_rev: int = 0
    # A layer resolver hit its except-fallback (missing dependency, DB error…).
    # The run still gets a usable intent, but it was composed from in-code
    # fallbacks rather than the real layer — so the Run can mark itself
    # degraded instead of reporting a clean compose.
    composed_degraded: bool = False
    degraded_layers: tuple[str, ...] = ()


def _note_degraded(sink: list[str] | None, layer: str) -> None:
    if sink is not None:
        sink.append(layer)


async def _resolve_platform_base(
    agent_key: str, *, degraded: list[str] | None = None
) -> str | None:
    """Enabled system body; None (→ in-code fallback) on miss/failure."""
    try:
        from domains.agents.services.registry import agent_body_by_key

        return await agent_body_by_key(agent_key)
    except Exception as exc:  # noqa: BLE001 — degrade to the in-code fallback
        logger.error(
            f"system agent resolution failed for {agent_key}: {type(exc).__name__}: {exc}",
            extra={"tag": "agents"},
        )
        _note_degraded(degraded, "platform_base")
        return None


async def _resolve_org_uid(
    repository_uid: str, *, degraded: list[str] | None = None
) -> str:
    try:
        from domains.llm_providers.services.llm_provider_service import repository_org_uid

        return await repository_org_uid(repository_uid) or ""
    except Exception as exc:  # noqa: BLE001 — no org ⇒ no override layer
        logger.error(
            f"org resolution failed for repository {repository_uid}: "
            f"{type(exc).__name__}: {exc}",
            extra={"tag": "agents"},
        )
        _note_degraded(degraded, "org_uid")
        return ""


async def _resolve_override(
    org_uid: str, agent_key: str, *, degraded: list[str] | None = None
):
    """(agent, active override revision | None) — never raises."""
    try:
        from domains.agents.services.agent_service import resolve_enabled_override
        from domains.agents.services.registry import system_agent_by_key

        agent = await system_agent_by_key(agent_key)
        if agent is None:
            return None, None
        return agent, await resolve_enabled_override(org_uid, agent)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            f"override resolution failed ({org_uid}/{agent_key}): "
            f"{type(exc).__name__}: {exc}",
            extra={"tag": "agents"},
        )
        _note_degraded(degraded, "override")
        return None, None


async def _resolve_repo_guidance_section(
    repository_uid: str, stage: str, *, degraded: list[str] | None = None
) -> str:
    """Rendered '## <Stage> guidance' section; "" on miss/failure."""
    if not stage or not repository_uid:
        return ""
    try:
        from domains.repositories.services.workflow import (
            guidance_section,
            stage_prompt_body,
        )

        return guidance_section(stage, await stage_prompt_body(repository_uid, stage))
    except Exception as exc:  # noqa: BLE001 — guidance is a layer, not a dependency
        logger.error(
            f"repo stage guidance resolution failed ({repository_uid}/{stage}): "
            f"{type(exc).__name__}: {exc}",
            extra={"tag": "agents"},
        )
        _note_degraded(degraded, "repo_guidance")
        return ""


def _render_repo_guidance(stage: str, body: str) -> str:
    from domains.repositories.services.workflow import guidance_section

    return guidance_section(stage or "stage", body)


async def compose_agent_intent(
    *,
    repository_uid: str,
    agent_key: str,
    structural: str = "",
    custom_intent: str | None = None,
    prompt_body: str | None = None,
    repo_guidance: str | None = None,
    stage: str | None = None,
    existing_state_listing: str = "",
    include_footer: bool | None = None,
    include_header: bool = True,
    org_uid: str | None = None,
) -> ComposedIntent:
    """Compose a run's first-turn intent with the org layers applied.

    - `agent_key` — the system agent supplying the instructions layer
      (usually the playbook name; deep-scan/generate-docs/audit-stale carry
      their own bases).
    - `structural` — the run's code-owned per-run contract (setup steps,
      target listings, verdict/reporting rules); lands in the scope slot,
      AFTER every guidance layer, so overrides can never displace it.
    - `custom_intent` — a run-specific instruction override (user prompt,
      specialized run template). Takes the instructions slot; a replace
      override does NOT substitute it (org guidance still appends).
    - `prompt_body` — a resolved Agent prompt (e.g. a user agent's own
      instructions); wins over the system base, loses to `custom_intent`.
    - `repo_guidance` — pre-resolved stage prompt body; None ⇒ resolve from
      the workflow config for `stage` (default: the key's stage); "" ⇒
      no repo guidance layer.
    - `include_footer` — default: every key except chat.

    Never raises for layer-resolution reasons: each layer degrades
    independently and the run always gets a usable intent.
    """
    from domains.agents.services.seed_agent_bases import agent_base_fallback
    from domains.runs.services._intent_helpers import build_intent

    if include_footer is None:
        include_footer = agent_key != "chat"
    if stage is None:
        stage = _KEY_STAGE.get(agent_key, "")

    degraded: list[str] = []
    resolved_org = (
        org_uid
        if org_uid is not None
        else await _resolve_org_uid(repository_uid, degraded=degraded)
    )
    platform_body = await _resolve_platform_base(agent_key, degraded=degraded)
    agent, override = await _resolve_override(
        resolved_org, agent_key, degraded=degraded
    )

    if repo_guidance is None:
        guidance_block = await _resolve_repo_guidance_section(
            repository_uid, stage, degraded=degraded
        )
    else:
        guidance_block = _render_repo_guidance(stage, repo_guidance)

    text = build_intent(
        custom_intent=custom_intent,
        prompt_body=prompt_body,
        platform_instructions=platform_body,
        default_intent=agent_base_fallback(agent_key) or f"Run the {agent_key} agent.",
        org_overlay_mode=(override.mode if override else ""),
        org_overlay_body=(override.body if override else ""),
        repo_guidance_section=guidance_block,
        scope_summary=structural,
        existing_state_listing=existing_state_listing,
        include_footer=include_footer,
        include_header=include_header,
    )
    return ComposedIntent(
        text=text,
        agent_uid=agent.uid if agent else "",
        agent_rev=int(override.rev or 0) if override else 0,
        composed_degraded=bool(degraded),
        degraded_layers=tuple(degraded),
    )


async def chat_instruction_layers(org_uid: str) -> str:
    """Chat's thinner wrapper: platform chat instructions + org guidance,
    with no framing header and no look-before-write footer. Appended to the
    code-owned chat contract in the first-turn preamble."""
    from domains.agents.services.seed_agent_bases import agent_base_fallback
    from domains.runs.services._intent_helpers import ORG_GUIDANCE_HEADING

    base = await _resolve_platform_base("chat")
    if base is None:
        base = agent_base_fallback("chat")
    _agent, override = await _resolve_override(org_uid, "chat")
    if override is not None and (override.mode or "") == OverlayMode.REPLACE:
        base = override.body or ""
    parts = [p for p in [(base or "").strip()] if p]
    if override is not None and (override.mode or "") == OverlayMode.APPEND and (override.body or "").strip():
        parts.append(f"{ORG_GUIDANCE_HEADING}\n\n{override.body.strip()}")
    return "\n\n".join(parts)


async def preview_composed_prompt(
    *, org_uid: str, agent_key: str, mode: str, body: str
) -> str:
    """The fully composed prompt for a DRAFT override (not persisted), using a
    representative scope stub — so editors see exactly what the agent gets."""
    from domains.agents.services.seed_agent_bases import agent_base_fallback
    from domains.runs.services._intent_helpers import build_intent

    platform_body = await _resolve_platform_base(agent_key)
    return build_intent(
        platform_instructions=platform_body,
        default_intent=agent_base_fallback(agent_key) or f"Run the {agent_key} agent.",
        org_overlay_mode=mode,
        org_overlay_body=body,
        repo_guidance_section=_render_repo_guidance(
            _KEY_STAGE.get(agent_key, ""),
            "(preview) The repository's configured stage guidance appears here "
            "on real runs, stacking on top of the layers above.",
        )
        if _KEY_STAGE.get(agent_key)
        else "",
        scope_summary=PREVIEW_SCOPE_STUB,
        include_footer=agent_key != "chat",
    )
