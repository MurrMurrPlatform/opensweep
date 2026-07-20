"""Celery wiring — beat entries exist and long-running work carries its own
time limits (a resumed CLI run must not run inside the global 600/900s box).
"""

import celery_app
import domains.runs.tasks.resume_paused as resume_paused_module  # noqa: F401 — registers tasks
from celery_app import app


def test_sandbox_cleanup_is_scheduled_every_30_minutes():
    beat = app.conf.beat_schedule
    entry = beat.get("sandbox-cleanup")
    assert entry is not None, "cleanup_sandboxes task existed but was never scheduled"
    assert entry["task"] == "opensweep.execution.cleanup_sandboxes"
    assert entry["schedule"] == 1800.0


def test_resume_beat_entry_still_scheduled():
    entry = app.conf.beat_schedule.get("run-resume-paused")
    assert entry is not None
    assert entry["task"] == "opensweep.runs.resume_paused_runs"


def test_resume_run_task_registered_with_long_limits():
    task = app.tasks.get("opensweep.runs.resume_run")
    assert task is not None, "per-run resume task missing — beat tick would redispatch inline"
    assert task.soft_time_limit == 3600
    assert task.time_limit == 3900


def test_global_limits_unchanged_for_ticks():
    assert celery_app.app.conf.task_soft_time_limit == 600
    assert celery_app.app.conf.task_time_limit == 900


def test_beat_scan_task_registered():
    assert app.tasks.get("opensweep.runs.resume_paused_runs") is not None


def test_campaign_tick_is_scheduled_every_minute():
    import domains.campaigns.tasks.campaign_tick as campaign_tick_module  # noqa: F401 — registers task

    entry = app.conf.beat_schedule.get("campaign-tick")
    assert entry is not None, "campaign tick must be beat-scheduled or parts never chain"
    assert entry["task"] == "opensweep.campaigns.tick"
    assert entry["schedule"] == 60.0
    assert app.tasks.get("opensweep.campaigns.tick") is not None
