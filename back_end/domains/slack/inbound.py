"""Inbound Slack traffic: Events API callbacks (@mention, DM) and the /opensweep
slash command.

Slack expects a 200 within 3 seconds, so the HTTP handlers (api/v1/slack.py)
ack immediately and hand the actual work — which clones a workspace and runs
LLM turns — to `asyncio.create_task(handle_conversation(...))`. Replies post
into the originating thread with the org's bot token.

Repository resolution for a question, in order:
  1. an explicit `repo:<slug>` token anywhere in the text,
  2. a bare token matching exactly one org repo's slug (or slug tail),
  3. the org's only repository, when it has exactly one.
Anything else gets a help reply listing the org's repos.
"""

from __future__ import annotations

import re

from domains.repositories.models import Repository
from domains.slack import chat as slack_chat
from domains.slack.client import SlackApiError, post_message
from domains.slack.models import SlackConnection
from domains.slack.service import bot_token
from logging_config import logger

_MENTION_RE = re.compile(r"<@[A-Z0-9]+>")
_REPO_TOKEN_RE = re.compile(r"repo:(\S+)", re.IGNORECASE)
_EVENT_DEDUPE_TTL_SECONDS = 600

HELP_TEXT = (
    "*OpenSweep* — repo intelligence from Slack :broom:\n"
    "• `/opensweep ask <question>` — ask about your code (add `repo:<slug>` when "
    "your org has several repositories)\n"
    "• `/opensweep repos` — list connected repositories\n"
    "• `/opensweep runs` — the five most recent runs\n"
    "• `/opensweep help` — this message\n"
    "You can also *@mention me* in a channel or DM me a question; follow-ups "
    "in the same thread continue the conversation."
)


def strip_mentions(text: str) -> str:
    return _MENTION_RE.sub("", text or "").strip()


async def already_processed(event_id: str) -> bool:
    """Dedupe Slack's at-least-once delivery (3s retry policy) by event_id.
    Redis loss fails open — better a rare duplicate answer than none."""
    if not event_id:
        return False
    from infrastructure import redis_client

    try:
        stored = await redis_client.get_async_redis().set(
            f"opensweep:slack:event:{event_id}", "1", ex=_EVENT_DEDUPE_TTL_SECONDS, nx=True
        )
        return not bool(stored)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Slack event dedupe skipped: {exc}", extra={"tag": "slack"})
        return False


async def org_repositories(org_uid: str) -> list[Repository]:
    return await Repository.nodes.filter(org_uid=org_uid)


def _match_repo(token: str, repos: list[Repository]) -> list[Repository]:
    token = token.strip().strip("`<>").lower()
    if not token:
        return []
    exact = [r for r in repos if (r.slug or "").lower() == token]
    if exact:
        return exact
    return [r for r in repos if (r.slug or "").lower().split("/")[-1] == token]


async def resolve_repository(
    org_uid: str, text: str
) -> tuple[Repository | None, str, str]:
    """(repository, question_without_repo_token, error_reply). Exactly one of
    repository / error_reply is set."""
    repos = await org_repositories(org_uid)
    if not repos:
        return None, text, "No repositories are registered for your organization yet."

    explicit = _REPO_TOKEN_RE.search(text)
    if explicit:
        matches = _match_repo(explicit.group(1), repos)
        question = (text[: explicit.start()] + text[explicit.end():]).strip()
        if len(matches) == 1:
            return matches[0], question, ""
        slugs = ", ".join(f"`{r.slug}`" for r in repos)
        return None, text, (
            f"I don't know the repository `{explicit.group(1)}`. "
            f"Your org's repositories: {slugs}"
        )

    # A bare token naming exactly one repo ("what does the repo's auth do?")
    candidates: dict[str, Repository] = {}
    for word in re.findall(r"[\w./-]+", text.lower()):
        for repo in _match_repo(word, repos):
            candidates[repo.uid] = repo
    if len(candidates) == 1:
        return next(iter(candidates.values())), text, ""

    if len(repos) == 1:
        return repos[0], text, ""

    slugs = ", ".join(f"`{r.slug}`" for r in repos)
    return None, text, (
        "Your organization has several repositories — tell me which one with "
        f"`repo:<slug>`. Available: {slugs}"
    )


async def handle_conversation(
    *,
    connection: SlackConnection,
    channel: str,
    thread_ts: str,
    slack_user: str,
    text: str,
    is_new_thread: bool,
    conversation_key: str = "",
) -> None:
    """Answer one inbound message (mention/DM/slash-ask). Runs as a background
    task: posts the reply — or the failure — into the thread itself.

    thread_ts="" (slash command — the invocation has no message timestamp; or
    a flat DM) anchors any thread on our own ack message instead.
    conversation_key identifies the rolling conversation for follow-ups
    (thread ts in channels, the channel itself in DMs); defaults to the
    posting anchor."""
    try:
        token = bot_token(connection)
    except Exception as exc:  # noqa: BLE001 — without a token there is no reply channel at all
        logger.error(
            f"Slack bot token unusable for org {connection.org_uid} "
            f"(team {connection.team_id}) — cannot answer {channel}: "
            f"{type(exc).__name__}: {exc}",
            extra={"tag": "slack"},
        )
        return
    question = strip_mentions(text)
    anchor = thread_ts

    async def _post(reply: str) -> str:
        nonlocal anchor
        try:
            data = await post_message(
                token, channel=channel, text=reply, thread_ts=anchor or None
            )
            if not anchor:
                anchor = str(data.get("ts") or "")
            return anchor
        except SlackApiError as exc:
            logger.warning(
                f"Slack reply to {channel} failed: {exc.error}", extra={"tag": "slack"}
            )
            return anchor

    if not question:
        await _post(HELP_TEXT)
        return

    try:
        # Follow-up in a mapped conversation continues it.
        key = conversation_key or anchor
        if not is_new_thread and key:
            reply = await slack_chat.continue_conversation(
                connection=connection,
                team_id=connection.team_id,
                channel=channel,
                conversation_key=key,
                question=question,
            )
            if reply is not None:
                await _post(reply)
                return

        repo, question, error_reply = await resolve_repository(connection.org_uid, question)
        if repo is None:
            await _post(error_reply)
            return

        await _post(
            f":hourglass_flowing_sand: Looking into `{repo.slug}` — "
            "I'll reply here in a few minutes."
        )
        reply = await slack_chat.answer_question(
            connection=connection,
            repository_uid=repo.uid,
            question=question,
            team_id=connection.team_id,
            channel=channel,
            thread_ts=anchor,
            conversation_key=conversation_key or anchor,
            slack_user=slack_user,
        )
        await _post(reply)
    except Exception as exc:  # noqa: BLE001 — the thread must hear about failures
        logger.warning(
            f"Slack conversation failed in {channel}: {type(exc).__name__}: {exc}",
            extra={"tag": "slack"},
        )
        # Human-actionable errors (no provider configured, repo not found)
        # are worth relaying; keep it short so internals don't spill out.
        detail = str(exc).strip()[:300]
        await _post(f":x: I couldn't finish that: {detail or type(exc).__name__}")


# ── /opensweep slash command ─────────────────────────────────────────────────────


def parse_command(text: str) -> tuple[str, str]:
    """(subcommand, remainder) — bare `/opensweep <question>` is treated as ask."""
    stripped = (text or "").strip()
    if not stripped:
        return "help", ""
    head, _, rest = stripped.partition(" ")
    head = head.lower()
    if head in {"help", "repos", "runs", "ask"}:
        return head, rest.strip()
    return "ask", stripped


async def command_repos_reply(org_uid: str) -> str:
    repos = await org_repositories(org_uid)
    if not repos:
        return "No repositories are registered yet — add one in OpenSweep first."
    lines = [f"• `{r.slug}`" for r in sorted(repos, key=lambda r: r.slug or "")]
    return "*Repositories:*\n" + "\n".join(lines)


async def command_runs_reply(org_uid: str) -> str:
    from domains.runs.models import Run
    from domains.slack.formatting import frontend_base_url

    repos = {r.uid: r for r in await org_repositories(org_uid)}
    if not repos:
        return "No repositories are registered yet."
    runs = await Run.nodes.filter(
        repository_uid__in=list(repos), surface="runs"
    ).order_by("-started_at")
    runs = list(runs)[:5]
    if not runs:
        return "No runs yet."
    base = frontend_base_url()
    lines = []
    for run in runs:
        repo = repos.get(run.repository_uid)
        slug = (repo.slug if repo else "") or "?"
        title = (run.title or run.playbook or "run").strip()
        label = f"{title} — {run.status} ({slug})"
        lines.append(f"• <{base}/runs/{run.uid}|{label}>" if base else f"• {label}")
    return "*Recent runs:*\n" + "\n".join(lines)
