"""Pure-Python pins for the seeded per-playbook platform bases
(opensweep://agent/<playbook>) — the task-instructions layer org overlays
apply to. DB writes are integration territory; here we pin the specs."""

from domains.agent_prompts.services.seed_agent_bases import (
    _AGENT_BASES,
    AGENT_PLAYBOOKS,
    agent_base_fallback,
    agent_source_url,
)
from domains.agent_prompts.services.seed_defaults import _DEFAULTS, workflow_source_url
from domains.agent_prompts.services.seed_variants import _VARIANTS, variant_source_url
from domains.investigations.services.job_types import get_job_type
from domains.investigations.services.playbooks import PLAYBOOKS

# Overlay-only agent keys: specialized sweep flows that run under the "ask"
# run playbook but carry their own seeded instruction bases.
_SWEEP_AGENTS = {"deep-scan", "generate-docs"}


def test_bases_cover_every_playbook_exactly():
    assert set(_AGENT_BASES) == PLAYBOOKS | _SWEEP_AGENTS
    assert set(AGENT_PLAYBOOKS) == PLAYBOOKS | _SWEEP_AGENTS
    assert len(AGENT_PLAYBOOKS) == 11


def test_base_specs_are_well_formed():
    for playbook, spec in _AGENT_BASES.items():
        assert spec["title"], playbook
        assert spec["description"], playbook
        assert spec["body"].strip(), playbook
        assert get_job_type(spec["default_job_type"]) is not None, playbook
        assert "opensweep-agent-base" in spec["tags"], playbook
        assert playbook in spec["tags"], playbook


def test_source_urls_are_opensweep_agent_uris_and_disjoint():
    base_urls = {agent_source_url(pb) for pb in _AGENT_BASES}
    assert base_urls == {f"opensweep://agent/{pb}" for pb in _AGENT_BASES}
    workflow_urls = {workflow_source_url(s) for s in _DEFAULTS}
    variant_urls = {variant_source_url(s) for s in _VARIANTS}
    assert not base_urls & workflow_urls
    assert not base_urls & variant_urls


def test_in_code_fallback_matches_the_shipped_body():
    """The last-resort fallback (used when the seeded row is deleted or
    disabled) is the same in-code string the seeder ships."""
    for playbook in AGENT_PLAYBOOKS:
        assert agent_base_fallback(playbook) == _AGENT_BASES[playbook]["body"]
    assert agent_base_fallback("nope") == ""


def test_bases_carry_task_instructions_not_structure():
    """Structural anchors (tool call sequences, shas, branch names, verdict
    plumbing) stay in code — the editable bodies must not hardcode them."""
    for playbook, spec in _AGENT_BASES.items():
        body = spec["body"]
        assert "git checkout" not in body, playbook
        assert "opensweep_platform_submit_verdict" not in body, playbook
        assert "{" not in body, f"{playbook}: no format placeholders in seeded bodies"


def test_write_playbooks_keep_the_never_push_rule():
    for playbook in ("fix", "implement"):
        assert "push" in _AGENT_BASES[playbook]["body"].lower(), playbook
