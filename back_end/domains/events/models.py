"""Audit Event node.

Events are created on every transition and exposed through the audit API
(api/v1/audit.py — `opensweep_list_audit_events` / `opensweep_get_audit_event`).
"""

from neomodel import (
    AsyncStructuredNode,
    DateTimeProperty,
    JSONProperty,
    StringProperty,
)


class Event(AsyncStructuredNode):
    uid = StringProperty(unique_index=True, required=True)
    kind = StringProperty(required=True)
    subject_uid = StringProperty(index=True)
    subject_type = StringProperty()  # Repository | Doc | Run | Finding
    actor_uid = StringProperty()
    # Tenancy: derived from the subject at write time (write_audit). Empty =
    # platform-level event (provider/app config) — admin-only in the API.
    repository_uid = StringProperty(index=True, default="")
    payload = JSONProperty(default={})
    occurred_at = DateTimeProperty(default_now=True)
