"""Helper used by Celery tasks: run a coroutine in a fresh event loop with
the async neomodel driver initialized.

Each `asyncio.run` creates a fresh event loop, but module-level singletons
(the neomodel `adb` driver, httpx clients) survive from the previous — now
closed — loop. Reusing them raises "Event loop is closed" or hangs. The entry
point here therefore ALWAYS reconnects the async driver to the current loop
(the pattern tasks/schedule_tick.py used inline, centralized).
"""

import asyncio
from typing import TypeVar

T = TypeVar("T")


async def _reconnect_async_driver() -> None:
    """Bind the neomodel async driver to the CURRENT event loop.

    Any existing driver was created on a previous (dead) loop: close it if
    possible, discard it otherwise, then connect fresh.
    """
    from neomodel import adb
    from neomodel import config as neomodel_conf

    db_url = getattr(neomodel_conf, "DATABASE_URL", None)
    if not db_url:
        return
    if adb.driver is not None:
        try:
            await adb.close_connection()
        except Exception:
            # Driver bound to a dead loop — closing it is impossible; drop it.
            adb.driver = None
    await adb.set_connection(url=db_url)


def run_async_task(coro_fn) -> T:
    """`coro_fn` is a 0-arg async function; we initialize the async driver,
    then call it. Returns its result.
    """
    async def _entry() -> T:
        await _reconnect_async_driver()
        return await coro_fn()

    return asyncio.run(_entry())
