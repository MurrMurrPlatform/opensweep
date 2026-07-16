"""Celery task delivering one audit event to Slack (enqueued by
domains/slack/notify.notify_slack_of_event from write_audit).

Deliberately no retries: per-channel Slack failures (including transport
errors, which the client wraps into SlackApiError) are caught and logged
inside deliver_audit_event, and re-running after a partial fan-out would
duplicate messages on the channels that already got one. Unexpected errors
(DB down) fail the task loudly in Celery instead."""

from celery_app import app
from domains.slack.notify import DELIVER_TASK_NAME


@app.task(name=DELIVER_TASK_NAME)
def deliver_event(event: dict) -> dict:
    from domains.slack.notify import deliver_audit_event
    from infrastructure.celery_async import run_async_task
    from infrastructure.neomodel_config import configure_neomodel

    configure_neomodel()

    async def _go() -> dict:
        return await deliver_audit_event(event)

    return run_async_task(_go)
