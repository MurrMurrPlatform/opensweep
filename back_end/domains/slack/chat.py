"""Slack → OpenSweep conversations: an @mention or DM runs a chat-playbook Run
whose reply posts back into the Slack thread.

Threading model: the first question creates a Run (surface="slack", hidden
from the Runs page); a conversation↔run mapping lives in Redis for 7 days so
follow-ups continue the same conversation (same workspace clone, full
transcript context) as extra turns. The conversation key is the Slack thread
ts in channels, and the DM channel itself in DMs — a DM is one rolling
conversation, not a new workspace clone per message.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from domains.runs.models import Run
from domains.runs.schemas import Playbook, RunStatus
from domains.slack.models import SlackConnection
from logging_config import logger

THREAD_TTL_SECONDS = 7 * 24 * 3600

# Statuses a mapped run can accept another turn in. Terminal/failed runs get
# a fresh run in the same thread instead of a dead-end error.
_CONTINUABLE_STATUSES = {RunStatus.AWAITING_INPUT.value}

SLACK_PREAMBLE = (
    "You are OpenSweep, answering a question asked from Slack about the "
    "repository cloned into your workspace (read-only — never modify code). "
    "You may use the opensweep_platform_* tools to look up findings, tickets, "
    "docs, and runs.\n"
    "Answer for Slack: be concise (a few short paragraphs at most), lead "
    "with the answer, and format with Slack mrkdwn (*bold*, `code`, code "
    "fences) — no markdown headers or tables."
)


def _conversation_redis_key(team_id: str, channel: str, key: str) -> str:
    return f"opensweep:slack:thread:{team_id}:{channel}:{key}"


async def _mapped_run_uid(team_id: str, channel: str, key: str) -> str:
    from infrastructure import redis_client

    try:
        return str(
            await redis_client.get_async_redis().get(
                _conversation_redis_key(team_id, channel, key)
            )
            or ""
        )
    except Exception as exc:  # noqa: BLE001 — Redis loss degrades to a fresh conversation
        logger.warning(f"Slack thread lookup skipped: {exc}", extra={"tag": "slack"})
        return ""


async def _remember_conversation(team_id: str, channel: str, key: str, run_uid: str) -> None:
    from infrastructure import redis_client

    try:
        await redis_client.get_async_redis().set(
            _conversation_redis_key(team_id, channel, key), run_uid, ex=THREAD_TTL_SECONDS
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Slack thread mapping skipped: {exc}", extra={"tag": "slack"})


async def _continuable_run(run_uid: str, org_uid: str) -> Run | None:
    """The mapped run, when it still belongs to this org and can take a turn."""
    if not run_uid:
        return None
    run = await Run.nodes.get_or_none(uid=run_uid)
    if run is None or run.status not in _CONTINUABLE_STATUSES:
        return None
    from domains.llm_providers.services.llm_provider_service import repository_org_uid

    if await repository_org_uid(run.repository_uid) != org_uid:
        return None
    return run


async def _create_slack_chat_run(
    *,
    repository_uid: str,
    org_uid: str,
    team_id: str,
    channel: str,
    thread_ts: str,
    slack_user: str,
) -> Run:
    """A chat-playbook Run with a ready discovery workspace (built inline —
    the caller already runs in a background task, so sequential prep keeps
    the first turn from racing the clone)."""
    from domains.execution.services.sandbox_service import SandboxService
    from domains.runs.services import workspace as workspace_service
    from domains.runs.services.lifecycle import (
        LifecycleError,
        _executor_for_provider,
    )
    from domains.runs.services.run_events import append_event
    from domains.llm_providers.services.llm_provider_service import select_provider
    from domains.repositories.services.repository_service import RepositoryService

    repository = await RepositoryService().get_repository(repository_uid, org_uid)
    provider = await select_provider(org_uid=org_uid)
    if provider is None:
        raise LifecycleError(
            "No LLM provider configured for this organization — an admin must "
            "add one in Settings → LLM Providers."
        )
    executor = _executor_for_provider(provider)

    now = datetime.now(UTC)
    run = Run(
        uid=uuid4().hex,
        repository_uid=repository.uid,
        playbook=Playbook.CHAT.value,
        title=f"Slack chat on {repository.slug}",
        executor=executor.value,
        execution_mode="analyze_only",
        provider_uid=(provider.uid or "").strip(),
        status=RunStatus.QUEUED.value,
        target={
            "slack_team_id": team_id,
            "slack_channel": channel,
            "slack_thread_ts": thread_ts,
            "slack_user": slack_user,
        },
        surface="slack",
        triggered_by=f"slack:{slack_user}",
        started_at=now,
        last_activity_at=now,
        usage={
            "provider_uid": (provider.uid or "").strip(),
            "provider_kind": (provider.kind or "").strip(),
        },
    )
    await run.save()

    sandbox = await SandboxService().create_for_discovery(
        repository=repository, agent_run_uid=run.uid
    )
    run.sandbox_uid = sandbox.uid
    run.workspace_spec = workspace_service.build_workspace_spec(sandbox, base_branch="")
    run.status = RunStatus.AWAITING_INPUT.value
    run.updated_at = datetime.now(UTC)
    await run.save()
    append_event(run.uid, "system", kind="sandbox", text="workspace ready")
    return run


async def _run_turn_collect(run_uid: str, prompt: str) -> str:
    """Execute one turn and return the assistant's full reply text."""
    from domains.runs.services.turn_service import TurnService

    content = ""
    error = ""
    async for event in TurnService().run_turn(run_uid, prompt):
        if event.get("type") == "message_complete":
            content = str(event.get("content") or "")
        elif event.get("type") == "error":
            error = str(event.get("detail") or "")
    if error:
        if not content:
            raise RuntimeError(error)
        # Partial answer: content exists but the turn also errored — the
        # Slack user gets the content; keep the error diagnosable.
        logger.warning(
            f"Slack chat turn on run {run_uid} errored after producing content: {error}",
            extra={"tag": "slack"},
        )
    return content


async def answer_question(
    *,
    connection: SlackConnection,
    repository_uid: str,
    question: str,
    team_id: str,
    channel: str,
    thread_ts: str,
    conversation_key: str,
    slack_user: str,
) -> str:
    """Answer a fresh Slack question: create the run, execute turn one, map
    the conversation. Returns the mrkdwn-ready reply text (raises on failure)."""
    from domains.slack.formatting import to_mrkdwn

    run = await _create_slack_chat_run(
        repository_uid=repository_uid,
        org_uid=connection.org_uid,
        team_id=team_id,
        channel=channel,
        thread_ts=thread_ts,
        slack_user=slack_user,
    )
    prompt = f"{SLACK_PREAMBLE}\n\n## The Slack user asks\n{question}"
    reply = await _run_turn_collect(run.uid, prompt)
    await _remember_conversation(team_id, channel, conversation_key, run.uid)
    return to_mrkdwn(reply) if reply else "I finished looking, but produced no reply text."


async def continue_conversation(
    *,
    connection: SlackConnection,
    team_id: str,
    channel: str,
    conversation_key: str,
    question: str,
) -> str | None:
    """Run a follow-up turn on the conversation's mapped run. None = nothing
    continuable mapped to this key (caller starts a fresh conversation)."""
    from domains.slack.formatting import to_mrkdwn

    run = await _continuable_run(
        await _mapped_run_uid(team_id, channel, conversation_key), connection.org_uid
    )
    if run is None:
        return None
    reply = await _run_turn_collect(run.uid, question)
    await _remember_conversation(team_id, channel, conversation_key, run.uid)
    return to_mrkdwn(reply) if reply else "I finished looking, but produced no reply text."
