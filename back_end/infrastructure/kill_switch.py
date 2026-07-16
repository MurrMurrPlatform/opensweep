"""Global + per-repo kill switches.

PLATFORM.md §Run policies: kill switches are first-class and halt all
autonomous and pending Run dispatches immediately. Human-triggered runs
receive a 409 at the API layer.

Storage:
- Per-repo: `Repository.kill_switch_active`
- Global:   `PlatformConfig` singleton (`uid='singleton'`)
"""

from __future__ import annotations

from datetime import datetime, timezone

from domains.repositories.models import PlatformConfig, Repository


_SINGLETON_UID = "singleton"


async def _platform_config() -> PlatformConfig:
    cfg = await PlatformConfig.nodes.get_or_none(uid=_SINGLETON_UID)
    if cfg is None:
        cfg = PlatformConfig(uid=_SINGLETON_UID, global_kill_switch=False)
        await cfg.save()
    return cfg


async def is_globally_halted() -> bool:
    cfg = await _platform_config()
    return bool(cfg.global_kill_switch)


async def set_global_kill_switch(active: bool) -> bool:
    cfg = await _platform_config()
    cfg.global_kill_switch = bool(active)
    cfg.updated_at = datetime.now(timezone.utc)
    await cfg.save()
    return cfg.global_kill_switch


async def is_repo_halted(repository_uid: str) -> bool:
    if await is_globally_halted():
        return True
    r = await Repository.nodes.get_or_none(uid=repository_uid)
    return bool(r and r.kill_switch_active)


async def set_repo_kill_switch(repository_uid: str, active: bool) -> bool:
    r = await Repository.nodes.get_or_none(uid=repository_uid)
    if r is None:
        return False
    r.kill_switch_active = bool(active)
    r.updated_at = datetime.now(timezone.utc)
    await r.save()
    return r.kill_switch_active


class KillSwitchActiveError(RuntimeError):
    """Raised by dispatch paths when a kill switch is set.

    API layers should catch and return HTTP 409.
    """

    def __init__(self, scope: str, repository_uid: str | None = None) -> None:
        self.scope = scope
        self.repository_uid = repository_uid
        super().__init__(
            f"kill switch active ({scope}{', repo=' + repository_uid if repository_uid else ''})"
        )


async def assert_runnable(repository_uid: str | None) -> None:
    """Raise KillSwitchActiveError if any kill switch blocks dispatch."""
    if await is_globally_halted():
        raise KillSwitchActiveError("global", repository_uid)
    if repository_uid and await is_repo_halted(repository_uid):
        raise KillSwitchActiveError("repository", repository_uid)
