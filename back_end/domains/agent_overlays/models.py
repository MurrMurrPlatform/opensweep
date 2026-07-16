"""Org agent overlays — per-organization tuning of each playbook's task
instructions (docs/superpowers/specs/2026-07-14-org-agent-overlays-design.md).

One `OrgAgentOverlay` per `(org_uid, playbook)` — enforced in the service
layer (get-or-create under a lock), as neomodel lacks composite unique
indexes. `mode="append"` adds the body under the platform instructions as an
"## Organization guidance" section; `mode="replace"` substitutes the
platform-instructions layer wholesale. The structural framing (header,
look-before-write footer, per-run contracts) stays in code and is never
editable through overlays.

`OrgAgentOverlayRevision` is the append-only history: one snapshot per save,
with a monotonic `rev` per `(org_uid, playbook)`. Revert copies an old
revision into a NEW head revision; revisions are never rewritten. Revisions
are keyed logically by `(org_uid, playbook)` (not just `overlay_uid`) so
history survives a delete + re-create of the overlay.
"""

from neomodel import (
    AsyncStructuredNode,
    BooleanProperty,
    DateTimeProperty,
    IntegerProperty,
    StringProperty,
)

OVERLAY_MODES = {"append", "replace"}

# Generous body cap (spec: ~32 KB). Enforced in the service with a clear 422.
OVERLAY_BODY_MAX_BYTES = 32 * 1024


class OrgAgentOverlay(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)

    org_uid = StringProperty(required=True, index=True)
    playbook = StringProperty(required=True, index=True)  # must be in AGENT_PLAYBOOKS

    mode = StringProperty(default="append")  # append | replace
    body = StringProperty(default="")  # markdown task guidance
    enabled = BooleanProperty(default=True)

    # Head revision number (mirrors the latest OrgAgentOverlayRevision.rev).
    rev = IntegerProperty(default=0)

    updated_by = StringProperty(default="")  # user uid of the last editor
    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)


class OrgAgentOverlayRevision(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)

    overlay_uid = StringProperty(default="", index=True)
    org_uid = StringProperty(required=True, index=True)
    playbook = StringProperty(required=True, index=True)

    rev = IntegerProperty(required=True)  # monotonic per (org_uid, playbook)
    mode = StringProperty(default="append")
    body = StringProperty(default="")
    enabled = BooleanProperty(default=True)

    author_uid = StringProperty(default="")
    created_at = DateTimeProperty(default_now=True)
