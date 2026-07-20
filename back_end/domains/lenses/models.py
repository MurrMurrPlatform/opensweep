"""Lens — the smallest reusable unit of audit focus.

A lens is one named discipline of scrutiny ("bugs", "security",
"test-gaps") whose `body` is a standalone prompt snippet: what to check,
what evidence a finding needs, and that "checked, nothing found" is a
valid verdict.

- `scope="local"` lenses compose into per-area run checklists
  (lens_service.lens_checklist): an area run works its lenses one at a
  time and reports a verdict per lens through complete_run's
  lens_verdicts.
- `scope="global"` lenses back whole-repo sweep agents — cross-cutting
  concerns (architecture, implementation gaps) that cannot be judged one
  area at a time. `global_agent_key` names the seeded variant slug
  (opensweep://library/<slug>) dispatched for them; area runs escalate
  out-of-scope observations to these via `escalate:<lens-key>` finding
  tags instead of investigating them.

Seeded rows (`provenance="system"`) carry a `seed_checksum` with the same
UPSERT/SYNC/FORCE semantics as the prompt library (services/seed_lenses.py
mirrors platform_prompts.upsert_platform_prompt), so shipped improvements
roll forward without clobbering org tuning.
"""

from neomodel import (
    AsyncStructuredNode,
    BooleanProperty,
    DateTimeProperty,
    JSONProperty,
    StringProperty,
)

LENS_SCOPES = {"local", "global"}


class Lens(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)
    key = StringProperty(unique_index=True, required=True)

    title = StringProperty(default="")
    scope = StringProperty(default="local", index=True)  # local | global
    body = StringProperty(default="")  # the prompt snippet
    tags = JSONProperty(default=[])
    # Pre-pass inputs the lens wants injected into its briefing
    # (e.g. "static_analysis" — candidate lines from the analyzer pass).
    wants = JSONProperty(default=[])
    # Global lenses only: the seeded variant slug to dispatch for the sweep.
    global_agent_key = StringProperty(default="")

    enabled = BooleanProperty(default=True)
    provenance = StringProperty(default="system")  # system | user
    seed_checksum = StringProperty(default="")

    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)
