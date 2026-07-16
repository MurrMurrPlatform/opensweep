"""Resolve LLM-provider metadata for a given Run.

Findings and Knowledge entries carry a `source_run_uid` only. The originating
provider is recorded inside the run's `usage` JSON at start time (see
`lifecycle.trigger_run`). When that snapshot is missing (older runs), fall
back to looking up the provider by uid so detail views can still display
a current label/model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from domains.investigations.models import Run
from domains.llm_providers.models import LLMProvider


@dataclass(frozen=True)
class RunProviderInfo:
    uid: Optional[str] = None
    label: str = ""
    kind: str = ""
    model: str = ""


_EMPTY = RunProviderInfo()


async def provider_info_for_run(run_uid: Optional[str]) -> RunProviderInfo:
    if not run_uid:
        return _EMPTY
    run = await Run.nodes.get_or_none(uid=run_uid)
    if run is None:
        return _EMPTY
    usage = run.usage or {}
    uid = (usage.get("provider_uid") or "").strip() or None
    label = (usage.get("provider_label") or "").strip()
    kind = (usage.get("provider_kind") or "").strip()
    model = (usage.get("provider_model") or "").strip()
    # Old runs only snapshotted `provider_kind`. Hydrate the rest from the
    # provider record when we can find it.
    if uid and (not label or not model):
        provider = await LLMProvider.nodes.get_or_none(uid=uid)
        if provider is not None:
            label = label or (provider.label or "").strip()
            kind = kind or (provider.kind or "").strip()
            model = model or (provider.model or "").strip()
    return RunProviderInfo(uid=uid, label=label, kind=kind, model=model)
