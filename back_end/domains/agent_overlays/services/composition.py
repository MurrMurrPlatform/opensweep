"""Layer resolution + intent composition for playbook runs.

The composed prompt (the cake — spec §Composition):

    OPENSWEEP_FRAMING_HEADER      code; always included
    <platform instructions>       seeded opensweep://agent/<playbook> body
                                  — or the org overlay body when mode=replace
    ## Organization guidance      org overlay body when mode=append
    ## <Stage> guidance           per-repo workflow-config prompt (unchanged)
    # Scope / existing state      the run's structural contract + scope
    LOOK_BEFORE_WRITE_FOOTER      code; unconditional (chat has none)

`build_intent` (investigations/_intent_helpers.py) does the pure assembly;
this module resolves the async layers — platform base, org overlay, repo
stage guidance — degrading ONE layer at a time with a log line. A dangling
or disabled row never fails a run: missing overlay ⇒ platform base as-is;
missing/disabled base ⇒ the in-code fallback instructions.
"""

from __future__ import annotations

from dataclasses import dataclass

from logging_config import logger

# Playbook → workflow stage whose per-repo prompt stacks as repo guidance.
# refine and chat have no workflow stage.
_PLAYBOOK_STAGE = {
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
    overlay_uid: str = ""
    overlay_rev: int = 0


async def _resolve_platform_base(playbook: str) -> str | None:
    """Enabled seeded base body; None (→ in-code fallback) on miss/failure."""
    try:
        from domains.agent_prompts.services.seed_agent_bases import agent_base_body

        return await agent_base_body(playbook)
    except Exception as exc:  # noqa: BLE001 — degrade to the in-code fallback
        logger.warning(
            f"platform base resolution failed for {playbook}: {type(exc).__name__}: {exc}",
            extra={"tag": "agent_overlays"},
        )
        return None


async def _resolve_org_uid(repository_uid: str) -> str:
    try:
        from domains.llm_providers.services.llm_provider_service import repository_org_uid

        return await repository_org_uid(repository_uid) or ""
    except Exception as exc:  # noqa: BLE001 — no org ⇒ no overlay layer
        logger.warning(
            f"org resolution failed for repository {repository_uid}: "
            f"{type(exc).__name__}: {exc}",
            extra={"tag": "agent_overlays"},
        )
        return ""


async def _resolve_repo_guidance_section(repository_uid: str, stage: str) -> str:
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
        logger.warning(
            f"repo stage guidance resolution failed ({repository_uid}/{stage}): "
            f"{type(exc).__name__}: {exc}",
            extra={"tag": "agent_overlays"},
        )
        return ""


def _render_repo_guidance(stage: str, body: str) -> str:
    from domains.repositories.services.workflow import guidance_section

    return guidance_section(stage or "stage", body)


async def compose_playbook_intent(
    *,
    repository_uid: str,
    playbook: str,
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
    """Compose a playbook run's first-turn intent with the org layers applied.

    - `structural` — the run's code-owned per-run contract (setup steps,
      target listings, verdict/reporting rules); lands in the scope slot,
      AFTER every guidance layer, so overlays can never displace it.
    - `custom_intent` — a run-specific instruction override (user prompt,
      specialized run template). Takes the instructions slot; a replace
      overlay does NOT substitute it (org guidance still appends).
    - `repo_guidance` — pre-resolved stage prompt body; None ⇒ resolve from
      the workflow config for `stage` (default: the playbook's stage); "" ⇒
      no repo guidance layer.
    - `include_footer` — default: every playbook except chat.

    Never raises for layer-resolution reasons: each layer degrades
    independently and the run always gets a usable intent.
    """
    from domains.agent_overlays.services.overlay_service import resolve_enabled_overlay
    from domains.agent_prompts.services.seed_agent_bases import agent_base_fallback
    from domains.runs.services._intent_helpers import build_intent

    if include_footer is None:
        include_footer = playbook != "chat"
    if stage is None:
        stage = _PLAYBOOK_STAGE.get(playbook, "")

    resolved_org = org_uid if org_uid is not None else await _resolve_org_uid(repository_uid)
    platform_body = await _resolve_platform_base(playbook)
    overlay = await resolve_enabled_overlay(resolved_org, playbook)

    if repo_guidance is None:
        guidance_block = await _resolve_repo_guidance_section(repository_uid, stage)
    else:
        guidance_block = _render_repo_guidance(stage, repo_guidance)

    text = build_intent(
        custom_intent=custom_intent,
        prompt_body=prompt_body,
        platform_instructions=platform_body,
        default_intent=agent_base_fallback(playbook) or f"Run the {playbook} playbook.",
        org_overlay_mode=(overlay.mode if overlay else ""),
        org_overlay_body=(overlay.body if overlay else ""),
        repo_guidance_section=guidance_block,
        scope_summary=structural,
        existing_state_listing=existing_state_listing,
        include_footer=include_footer,
        include_header=include_header,
    )
    return ComposedIntent(
        text=text,
        overlay_uid=overlay.uid if overlay else "",
        overlay_rev=int(overlay.rev or 0) if overlay else 0,
    )


async def chat_instruction_layers(org_uid: str) -> str:
    """Chat's thinner wrapper: platform chat instructions + org guidance,
    with no framing header and no look-before-write footer. Appended to the
    code-owned chat contract in the first-turn preamble."""
    from domains.agent_overlays.services.overlay_service import resolve_enabled_overlay
    from domains.agent_prompts.services.seed_agent_bases import agent_base_fallback
    from domains.runs.services._intent_helpers import ORG_GUIDANCE_HEADING

    base = await _resolve_platform_base("chat")
    if base is None:
        base = agent_base_fallback("chat")
    overlay = await resolve_enabled_overlay(org_uid, "chat")
    if overlay is not None and (overlay.mode or "") == "replace":
        base = overlay.body or ""
    parts = [p for p in [(base or "").strip()] if p]
    if overlay is not None and (overlay.mode or "") == "append" and (overlay.body or "").strip():
        parts.append(f"{ORG_GUIDANCE_HEADING}\n\n{overlay.body.strip()}")
    return "\n\n".join(parts)


async def preview_composed_prompt(
    *, org_uid: str, playbook: str, mode: str, body: str
) -> str:
    """The fully composed prompt for a DRAFT overlay (not persisted), using a
    representative scope stub — so editors see exactly what the agent gets."""
    from domains.agent_prompts.services.seed_agent_bases import agent_base_fallback
    from domains.runs.services._intent_helpers import build_intent

    platform_body = await _resolve_platform_base(playbook)
    return build_intent(
        platform_instructions=platform_body,
        default_intent=agent_base_fallback(playbook) or f"Run the {playbook} playbook.",
        org_overlay_mode=mode,
        org_overlay_body=body,
        repo_guidance_section=_render_repo_guidance(
            _PLAYBOOK_STAGE.get(playbook, ""),
            "(preview) The repository's configured stage guidance appears here "
            "on real runs, stacking on top of the layers above.",
        )
        if _PLAYBOOK_STAGE.get(playbook)
        else "",
        scope_summary=PREVIEW_SCOPE_STUB,
        include_footer=playbook != "chat",
    )
