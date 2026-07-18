"""`opensweep connect` entitlement extension point (open-core seam).

The public product allows every org to connect local agents. OpenSweep Cloud
replaces CONNECT_ENTITLEMENT_HOOK at startup (additive overlay module) to
gate the consent step on the org's plan — never an `if cloud:` branch here.
"""

from __future__ import annotations

from typing import Awaitable, Callable


async def _allow_everything(org_uid: str) -> bool:  # noqa: ARG001
    return True


CONNECT_ENTITLEMENT_HOOK: Callable[[str], Awaitable[bool]] = _allow_everything


async def can_use_connect(org_uid: str) -> bool:
    return await CONNECT_ENTITLEMENT_HOOK(org_uid)
