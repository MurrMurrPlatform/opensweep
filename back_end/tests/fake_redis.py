"""Dict-backed stand-in for redis.asyncio.Redis (decode_responses=True).

Covers exactly the surface OpenSweep uses for state nonces + the installation
token L2 cache: get / set(ex=, nx=) / delete(*keys) / scan_iter / scan.
Set `raise_exc` to make every operation raise (Redis-outage simulation).
"""

from __future__ import annotations

import fnmatch


class FakeAsyncRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ex_by_key: dict[str, int | None] = {}
        self.raise_exc: Exception | None = None

    def _maybe_raise(self) -> None:
        if self.raise_exc is not None:
            raise self.raise_exc

    async def get(self, key: str) -> str | None:
        self._maybe_raise()
        return self.store.get(key)

    async def set(self, key: str, value, ex: int | None = None, nx: bool = False):
        self._maybe_raise()
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        self.ex_by_key[key] = ex
        return True

    async def delete(self, *keys: str) -> int:
        self._maybe_raise()
        count = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                self.ex_by_key.pop(key, None)
                count += 1
        return count

    async def scan_iter(self, match: str = "*", count: int | None = None):
        self._maybe_raise()
        for key in list(self.store.keys()):
            if fnmatch.fnmatch(key, match):
                yield key

    async def scan(self, cursor: int = 0, match: str = "*", count: int | None = None):
        self._maybe_raise()
        return 0, [k for k in list(self.store.keys()) if fnmatch.fnmatch(k, match)]
