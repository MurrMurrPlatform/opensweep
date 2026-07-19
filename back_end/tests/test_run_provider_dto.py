"""run_to_dto() maps the Run.usage provider_* snapshot onto RunDTO — the
same provider/model info that FindingDTO already surfaces via
provider_info_for_run(), now visible on runs (RunDetailView.vue)."""

from domains.runs.models import Run
from domains.runs.services.turn_service import run_to_dto


def test_run_to_dto_maps_provider_fields_from_usage_snapshot():
    run = Run(
        uid="run-1",
        repository_uid="repo-1",
        executor="claude_code",
        provider_uid="prov-1",
        usage={
            "provider_kind": "claude_api",
            "provider_label": "Anthropic API",
            "provider_model": "claude-sonnet-5",
        },
    )

    dto = run_to_dto(run)

    assert dto.provider_uid == "prov-1"
    assert dto.provider_label == "Anthropic API"
    assert dto.provider_kind == "claude_api"
    assert dto.provider_model == "claude-sonnet-5"


def test_run_to_dto_blanks_provider_fields_for_legacy_runs():
    run = Run(uid="run-2", repository_uid="repo-1", executor="codex", usage={})

    dto = run_to_dto(run)

    assert dto.provider_uid is None
    assert dto.provider_label == ""
    assert dto.provider_kind == ""
    assert dto.provider_model == ""
