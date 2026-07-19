"""Composition matrix for the org-agent-overlays cake (pure build_intent).

Spec (2026-07-14-org-agent-overlays-design.md §Composition):

    HEADER → platform instructions (or overlay body when replace)
           → "## Organization guidance" (append)
           → repo stage guidance → scope/state → FOOTER

Matrix: (no overlay | append | replace | disabled) ×
        (platform base present | admin-edited | disabled/missing) ×
        (repo guidance present | absent).
Header/footer are always present; replace never removes repo guidance,
scope, or the footer.
"""

import pytest

from domains.runs.services._intent_helpers import (
    LOOK_BEFORE_WRITE_FOOTER,
    OPENSWEEP_FRAMING_HEADER,
    ORG_GUIDANCE_HEADING,
    build_intent,
)
from domains.repositories.services.workflow import guidance_section

FALLBACK = "In-code fallback task instructions."
BASE = "Seeded platform instructions for the playbook."
EDITED_BASE = "Admin-edited platform instructions."
OVERLAY = "Org overlay guidance body."
REPO = guidance_section("review", "Repo stage guidance body.")
SCOPE = "Structural per-run contract: review PR #7 at sha abc123."

_HEADER_MARK = "You are OpenSweep"
_FOOTER_MARK = "# Look-before-write contract"


def compose(*, overlay_mode="", overlay_body="", platform=BASE, repo=REPO, scope=SCOPE):
    return build_intent(
        default_intent=FALLBACK,
        platform_instructions=platform,
        org_overlay_mode=overlay_mode,
        org_overlay_body=overlay_body,
        repo_guidance_section=repo,
        scope_summary=scope,
    )


# ── The full matrix: header/footer always, layers stack in spec order ───────

_OVERLAY_CASES = {
    "none": dict(overlay_mode="", overlay_body=""),
    "append": dict(overlay_mode="append", overlay_body=OVERLAY),
    "replace": dict(overlay_mode="replace", overlay_body=OVERLAY),
    # A disabled overlay is resolved to "no overlay" by the service layer —
    # build_intent sees empty mode/body (same as "none").
    "disabled": dict(overlay_mode="", overlay_body=""),
}
_BASE_CASES = {
    "present": BASE,
    "admin_edited": EDITED_BASE,
    # Disabled/missing base row → resolution passes None → in-code fallback.
    "disabled": None,
}
_REPO_CASES = {"present": REPO, "absent": ""}


@pytest.mark.parametrize("overlay_case", list(_OVERLAY_CASES))
@pytest.mark.parametrize("base_case", list(_BASE_CASES))
@pytest.mark.parametrize("repo_case", list(_REPO_CASES))
def test_matrix_header_and_footer_are_unconditional(overlay_case, base_case, repo_case):
    out = compose(
        **_OVERLAY_CASES[overlay_case],
        platform=_BASE_CASES[base_case],
        repo=_REPO_CASES[repo_case],
    )
    assert _HEADER_MARK in out
    assert _FOOTER_MARK in out
    assert out.strip().startswith(OPENSWEEP_FRAMING_HEADER.strip().splitlines()[0])
    assert out.rstrip().endswith(LOOK_BEFORE_WRITE_FOOTER.strip().splitlines()[-1])
    # Scope (the structural contract) is never displaced by any layer combo.
    assert SCOPE in out


@pytest.mark.parametrize("base_case", list(_BASE_CASES))
@pytest.mark.parametrize("repo_case", list(_REPO_CASES))
def test_matrix_instruction_layer_resolution(base_case, repo_case):
    """No overlay: platform body (seeded or admin-edited) wins; a disabled/
    missing base degrades to the in-code fallback."""
    out = compose(platform=_BASE_CASES[base_case], repo=_REPO_CASES[repo_case])
    expected = _BASE_CASES[base_case] or FALLBACK
    assert expected in out
    if repo_case == "present":
        assert "Repo stage guidance body." in out
    assert ORG_GUIDANCE_HEADING not in out


def test_append_places_org_guidance_between_instructions_and_repo_guidance():
    out = compose(overlay_mode="append", overlay_body=OVERLAY)
    assert out.index(_HEADER_MARK) < out.index(BASE)
    assert out.index(BASE) < out.index(ORG_GUIDANCE_HEADING)
    assert out.index(ORG_GUIDANCE_HEADING) < out.index("Repo stage guidance body.")
    assert out.index("Repo stage guidance body.") < out.index(SCOPE)
    assert out.index(SCOPE) < out.index(_FOOTER_MARK)


def test_replace_substitutes_only_the_platform_instructions_layer():
    out = compose(overlay_mode="replace", overlay_body=OVERLAY)
    assert OVERLAY in out
    assert BASE not in out  # the platform layer was substituted…
    assert "Repo stage guidance body." in out  # …but repo guidance stays
    assert SCOPE in out  # …the structural contract stays
    assert _HEADER_MARK in out and _FOOTER_MARK in out  # …and the framing stays
    assert ORG_GUIDANCE_HEADING not in out  # replace adds no append section


def test_replace_with_admin_edited_base_still_substitutes():
    out = compose(overlay_mode="replace", overlay_body=OVERLAY, platform=EDITED_BASE)
    assert OVERLAY in out
    assert EDITED_BASE not in out


def test_replace_with_missing_base_substitutes_the_fallback():
    out = compose(overlay_mode="replace", overlay_body=OVERLAY, platform=None)
    assert OVERLAY in out
    assert FALLBACK not in out


def test_custom_intent_override_wins_over_a_replace_overlay():
    """A run-specific instruction override (user prompt, specialized run
    template) is never displaced by an org overlay."""
    out = build_intent(
        custom_intent="Find SQL injection in the api layer.",
        default_intent=FALLBACK,
        platform_instructions=BASE,
        org_overlay_mode="replace",
        org_overlay_body=OVERLAY,
        repo_guidance_section=REPO,
        scope_summary=SCOPE,
    )
    assert "Find SQL injection in the api layer." in out
    assert OVERLAY not in out


def test_custom_intent_still_gets_append_guidance():
    out = build_intent(
        custom_intent="Find SQL injection in the api layer.",
        default_intent=FALLBACK,
        org_overlay_mode="append",
        org_overlay_body=OVERLAY,
    )
    assert "Find SQL injection in the api layer." in out
    assert ORG_GUIDANCE_HEADING in out
    assert OVERLAY in out


def test_empty_overlay_body_adds_no_section():
    out = compose(overlay_mode="append", overlay_body="   ")
    assert ORG_GUIDANCE_HEADING not in out
    out = compose(overlay_mode="replace", overlay_body="")
    assert BASE in out  # nothing to replace with — base survives
