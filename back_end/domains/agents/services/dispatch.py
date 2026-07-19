"""Dispatch bridge: Agent / ScheduledAgent → runs.lifecycle.trigger_run.

The ONLY module that turns agent configuration into an actual Run. It
composes the intent (system base or user prompt + org override + repo
stage guidance + target scope), maps `produces` onto the internal playbook,
resolves effort → run policy, and stamps provenance
(`scheduled_agent_uid`, `agent_uid`, `agent_rev`) on the Run.

Write agents (produces="code-changes") are refused outright: write runs
need a prepared write sandbox and ticket/PR context, which only the
delivery/thread services provide.
"""

from __future__ import annotations

from typing import Any

from domains.agents.models import Agent, ScheduledAgent
from domains.agents.services.composition import compose_agent_intent
from domains.agents.services.registry import (
    agent_key,
    playbook_for_produces,
    stage_for_agent_key,
)
from domains.runs.schemas import Effort, RunTrigger, normalize_effort


def _scope_summary(target: dict[str, Any]) -> str:
    """Human-readable scope block for the composed intent."""
    parts: list[str] = []
    paths = [str(p) for p in (target.get("paths") or []) if str(p).strip()]
    doc_uids = [str(d) for d in (target.get("doc_uids") or []) if str(d).strip()]
    if paths:
        parts.append("Limit the investigation to these repository paths:\n" +
                      "\n".join(f"- {p}" for p in paths))
    if doc_uids:
        parts.append("Scope: the documentation pages with uids " + ", ".join(doc_uids))
    if not parts:
        parts.append("Scope: the whole repository.")
    return "\n\n".join(parts)


async def dispatch_agent(
    *,
    agent: Agent,
    repository_uid: str,
    target: dict[str, Any] | None = None,
    effort: str = "",
    run_policy_uid: str | None = None,
    scheduled_agent_uid: str = "",
    trigger: RunTrigger = RunTrigger.MANUAL,
    triggered_by: str = "",
    title: str = "",
):
    """Compose and dispatch one run of an Agent on a repository."""
    from domains.run_policies.services.effort import ensure_policy_for_effort
    from domains.runs.services.lifecycle import LifecycleError, trigger_run

    if (agent.produces or "") == "code-changes":
        raise LifecycleError(
            "code-changes agents cannot be dispatched directly — write runs "
            "flow through the delivery pipeline"
        )
    if not agent.enabled:
        raise LifecycleError(f"Agent {agent.uid} is disabled")

    key = agent_key(agent.source_url or "")
    playbook = playbook_for_produces(agent.produces or "findings")
    target = dict(target or {})

    is_system = (agent.provenance or "") == "system" and key
    composed = await compose_agent_intent(
        repository_uid=repository_uid,
        agent_key=key if is_system else playbook,
        # A user/imported agent's own prompt takes the instructions slot; a
        # system agent's prompt IS the platform base and resolves by key.
        prompt_body=None if is_system else (agent.prompt or ""),
        structural=_scope_summary(target),
    )

    resolved_effort = (effort or agent.default_effort or "normal").strip()
    policy_uid = run_policy_uid
    if not policy_uid:
        policy = await ensure_policy_for_effort(normalize_effort(resolved_effort))
        policy_uid = policy.uid

    return await trigger_run(
        repository_uid=repository_uid,
        intent=composed.text,
        playbook=playbook,
        title=title or agent.title,
        target=target,
        run_policy_uid=policy_uid,
        trigger=trigger,
        triggered_by=triggered_by,
        scheduled_agent_uid=scheduled_agent_uid,
        agent_uid=agent.uid,
        agent_rev=composed.agent_rev,
        stage=stage_for_agent_key(key, playbook),
    )


async def trigger_scheduled_agent(
    scheduled_agent_uid: str,
    *,
    trigger: RunTrigger = RunTrigger.MANUAL,
    triggered_by: str = "",
):
    """Dispatch one run for a ScheduledAgent binding."""
    from domains.runs.services.lifecycle import LifecycleError

    s = await ScheduledAgent.nodes.get_or_none(uid=scheduled_agent_uid)
    if s is None:
        raise LifecycleError(f"ScheduledAgent {scheduled_agent_uid} not found")
    agent = await Agent.nodes.get_or_none(uid=s.agent_uid)
    if agent is None:
        raise LifecycleError(f"Agent {s.agent_uid} (bound by {s.uid}) not found")
    return await dispatch_agent(
        agent=agent,
        repository_uid=s.repository_uid,
        target=dict(s.target or {}),
        effort=s.effort or "",
        run_policy_uid=s.run_policy_uid or None,
        scheduled_agent_uid=s.uid,
        trigger=trigger,
        triggered_by=triggered_by,
        title=s.title or agent.title,
    )
