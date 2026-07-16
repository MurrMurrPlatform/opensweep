"""Org agent overlay service — uniqueness, revisions, revert, tenancy,
permissions surface, audit, preview, body cap. DB-free: the neomodel classes
are monkeypatched with in-memory fakes (same pattern as the LLM-provider
tenancy tests)."""

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

import domains.agent_overlays.services.overlay_service as svc
from domains.agent_overlays.models import OVERLAY_BODY_MAX_BYTES

pytestmark = pytest.mark.asyncio


# ── In-memory fakes ──────────────────────────────────────────────────────────


class _Node:
    _defaults: dict = {}
    _store: list

    def __init__(self, **kw):
        values = dict(self._defaults)
        values.update(kw)
        self.__dict__.update(values)

    async def save(self):
        if self not in self._store:
            self._store.append(self)
        return self

    async def delete(self):
        self._store.remove(self)


class _Nodes:
    def __init__(self, store):
        self._store = store

    async def all(self):
        return list(self._store)

    async def filter(self, **kw):
        return [
            n for n in self._store
            if all(getattr(n, k, None) == v for k, v in kw.items())
        ]

    async def get_or_none(self, **kw):
        rows = await self.filter(**kw)
        return rows[0] if rows else None


_OVERLAYS: list = []
_REVISIONS: list = []


class FakeOverlay(_Node):
    _store = _OVERLAYS
    _defaults = dict(
        uid="", org_uid="", playbook="", mode="append", body="", enabled=True,
        rev=0, updated_by="", created_at=None, updated_at=None,
    )
    nodes = _Nodes(_OVERLAYS)


class FakeRevision(_Node):
    _store = _REVISIONS
    _defaults = dict(
        uid="", overlay_uid="", org_uid="", playbook="", rev=0, mode="append",
        body="", enabled=True, author_uid="", created_at=None,
    )
    nodes = _Nodes(_REVISIONS)


AUDITS: list[dict] = []


@pytest.fixture(autouse=True)
def fake_overlays(monkeypatch):
    _OVERLAYS.clear()
    _REVISIONS.clear()
    AUDITS.clear()
    monkeypatch.setattr(svc, "OrgAgentOverlay", FakeOverlay)
    monkeypatch.setattr(svc, "OrgAgentOverlayRevision", FakeRevision)

    async def capture_audit(**kw):
        AUDITS.append(kw)

    monkeypatch.setattr(svc, "write_audit", capture_audit)
    svc._UPSERT_LOCKS.clear()
    yield
    _OVERLAYS.clear()
    _REVISIONS.clear()


async def _put(org="org-a", playbook="review", mode="append", body="Guidance.",
               enabled=True, actor="u1"):
    return await svc.upsert_overlay(
        org_uid=org, playbook=playbook, mode=mode, body=body,
        enabled=enabled, actor_uid=actor,
    )


# ── Validation ───────────────────────────────────────────────────────────────


async def test_unknown_playbook_is_422():
    with pytest.raises(HTTPException) as exc:
        await _put(playbook="deploy")
    assert exc.value.status_code == 422


async def test_sweep_agents_are_overlayable():
    # deep-scan and generate-docs are overlay-only agent keys (they run under
    # the "ask" run playbook) — the Agents page must accept overlays for them.
    for key in ("deep-scan", "generate-docs"):
        node = await _put(playbook=key, body=f"Org guidance for {key}.")
        assert node.rev == 1


async def test_invalid_mode_is_422():
    with pytest.raises(HTTPException) as exc:
        await _put(mode="prepend")
    assert exc.value.status_code == 422


async def test_body_over_32kb_is_422_with_clear_message():
    with pytest.raises(HTTPException) as exc:
        await _put(body="x" * (OVERLAY_BODY_MAX_BYTES + 1))
    assert exc.value.status_code == 422
    assert "32 KB" in exc.value.detail


async def test_body_at_the_cap_is_accepted():
    node = await _put(body="x" * OVERLAY_BODY_MAX_BYTES)
    assert node.rev == 1


async def test_orgless_caller_is_422():
    with pytest.raises(HTTPException) as exc:
        await _put(org="")
    assert exc.value.status_code == 422


# ── Uniqueness under concurrent upsert ───────────────────────────────────────


async def test_concurrent_upserts_yield_one_overlay_and_all_revisions():
    await asyncio.gather(*[_put(body=f"v{i}") for i in range(6)])
    assert len(_OVERLAYS) == 1  # one node per (org, playbook)
    revs = sorted(int(r.rev) for r in _REVISIONS)
    assert revs == [1, 2, 3, 4, 5, 6]  # every save snapshotted, revs unique
    assert int(_OVERLAYS[0].rev) == 6


async def test_different_playbooks_and_orgs_get_their_own_overlay():
    await _put(playbook="review")
    await _put(playbook="fix")
    await _put(org="org-b", playbook="review")
    assert len(_OVERLAYS) == 3


# ── Revision monotonicity + revert ───────────────────────────────────────────


async def test_revisions_are_monotonic_and_survive_delete():
    await _put(body="v1")
    await _put(body="v2")
    await svc.delete_overlay(org_uid="org-a", playbook="review", actor_uid="u1")
    assert _OVERLAYS == []  # overlay gone…
    assert len(_REVISIONS) == 2  # …history kept
    node = await _put(body="v3")
    assert int(node.rev) == 3  # rev sequence continues across the delete


async def test_revert_creates_a_new_head_copying_the_old_revision():
    await _put(body="v1", mode="append")
    await _put(body="v2", mode="replace")
    node = await svc.revert_overlay(
        org_uid="org-a", playbook="review", rev=1, actor_uid="u2"
    )
    assert int(node.rev) == 3  # new head, history append-only
    assert node.body == "v1"
    assert node.mode == "append"
    assert node.enabled is True
    revs = await svc.list_revisions("org-a", "review")
    assert [r.rev for r in revs] == [3, 2, 1]
    assert revs[0].author_uid == "u2"


async def test_revert_to_missing_rev_is_404():
    await _put(body="v1")
    with pytest.raises(HTTPException) as exc:
        await svc.revert_overlay(org_uid="org-a", playbook="review", rev=99, actor_uid="u1")
    assert exc.value.status_code == 404


async def test_delete_without_overlay_is_404():
    with pytest.raises(HTTPException) as exc:
        await svc.delete_overlay(org_uid="org-a", playbook="review", actor_uid="u1")
    assert exc.value.status_code == 404


# ── Tenancy isolation ────────────────────────────────────────────────────────


async def test_org_a_never_sees_or_affects_org_b():
    await _put(org="org-b", body="theirs")
    # read isolation
    assert await svc.get_overlay("org-a", "review") is None
    assert await svc.list_revisions("org-a", "review") == []
    assert await svc.active_overlay_provenance("org-a", "review") == ("", 0)
    # write isolation: delete/revert scoped to org-a cannot touch org-b's
    with pytest.raises(HTTPException):
        await svc.delete_overlay(org_uid="org-a", playbook="review", actor_uid="ua")
    with pytest.raises(HTTPException):
        await svc.revert_overlay(org_uid="org-a", playbook="review", rev=1, actor_uid="ua")
    assert len(_OVERLAYS) == 1 and _OVERLAYS[0].org_uid == "org-b"


async def test_resolution_is_scoped_to_the_org():
    await _put(org="org-a", body="mine")
    await _put(org="org-b", body="theirs")
    mine = await svc.resolve_enabled_overlay("org-a", "review")
    assert mine.body == "mine"


# ── Resolution degrades, never raises ────────────────────────────────────────


async def test_disabled_overlay_resolves_to_none():
    await _put(enabled=False)
    assert await svc.resolve_enabled_overlay("org-a", "review") is None
    assert await svc.active_overlay_provenance("org-a", "review") == ("", 0)


async def test_empty_body_overlay_resolves_to_none():
    await _put(body="   ")
    assert await svc.resolve_enabled_overlay("org-a", "review") is None


async def test_resolution_failure_degrades_to_none(monkeypatch):
    class Broken:
        class nodes:
            @staticmethod
            async def filter(**kw):
                raise RuntimeError("db down")

    monkeypatch.setattr(svc, "OrgAgentOverlay", Broken)
    assert await svc.resolve_enabled_overlay("org-a", "review") is None
    assert await svc.active_overlay_provenance("org-a", "review") == ("", 0)


# ── Audit + attribution ──────────────────────────────────────────────────────


async def test_mutations_write_audit_with_actor():
    await _put(actor="alice")
    await svc.revert_overlay(org_uid="org-a", playbook="review", rev=1, actor_uid="bob")
    await svc.delete_overlay(org_uid="org-a", playbook="review", actor_uid="carol")
    kinds = [a["kind"] for a in AUDITS]
    assert kinds == [
        "agent_overlay.updated",
        "agent_overlay.reverted",
        "agent_overlay.deleted",
    ]
    assert [a["actor_uid"] for a in AUDITS] == ["alice", "bob", "carol"]
    assert AUDITS[1]["payload"]["reverted_to_rev"] == 1


async def test_last_editor_is_attributed_on_the_overlay():
    await _put(actor="alice")
    node = await _put(actor="bob", body="v2")
    assert node.updated_by == "bob"
    assert isinstance(node.updated_at, datetime)
    assert node.updated_at.tzinfo == UTC


# ── Preview does not persist ─────────────────────────────────────────────────


async def test_preview_composes_without_persisting(monkeypatch):
    from domains.agent_overlays.services import composition

    async def fake_base(playbook):
        return "Seeded review instructions."

    monkeypatch.setattr(composition, "_resolve_platform_base", fake_base)
    prompt = await composition.preview_composed_prompt(
        org_uid="org-a", playbook="review", mode="append", body="Draft org guidance."
    )
    assert "Seeded review instructions." in prompt
    assert "## Organization guidance" in prompt
    assert "Draft org guidance." in prompt
    assert "You are OpenSweep" in prompt  # header
    assert "# Look-before-write contract" in prompt  # footer
    assert _OVERLAYS == [] and _REVISIONS == []  # nothing persisted
    assert AUDITS == []  # preview is not a mutation


async def test_preview_replace_substitutes_the_platform_layer(monkeypatch):
    from domains.agent_overlays.services import composition

    async def fake_base(playbook):
        return "Seeded review instructions."

    monkeypatch.setattr(composition, "_resolve_platform_base", fake_base)
    prompt = await composition.preview_composed_prompt(
        org_uid="org-a", playbook="review", mode="replace", body="Org replacement."
    )
    assert "Org replacement." in prompt
    assert "Seeded review instructions." not in prompt
    assert "# Look-before-write contract" in prompt


# ── Listing (platform base preview + overlay status) ─────────────────────────


async def test_list_playbook_statuses_covers_every_playbook(monkeypatch):
    from domains.agent_prompts.services import seed_agent_bases

    async def no_base(playbook):
        return None

    monkeypatch.setattr(
        "domains.agent_prompts.services.seed_agent_bases.agent_base_prompt", no_base
    )
    await _put(playbook="review", body="mine")
    statuses = await svc.list_playbook_statuses("org-a")
    assert [s.playbook for s in statuses] == list(seed_agent_bases.AGENT_PLAYBOOKS)
    by_pb = {s.playbook: s for s in statuses}
    assert by_pb["review"].overlay is not None
    assert by_pb["review"].overlay.body == "mine"
    assert by_pb["fix"].overlay is None


# ── Dispatch-path composition (compose_playbook_intent) ──────────────────────


async def test_compose_places_org_guidance_between_platform_and_repo_layers(monkeypatch):
    """The wiring the review trigger uses: platform instructions → org
    guidance → repo stage guidance → structural contract, with provenance."""
    from domains.agent_overlays.services import composition

    async def fake_base(playbook):
        return "Seeded review instructions."

    monkeypatch.setattr(composition, "_resolve_platform_base", fake_base)
    await _put(playbook="review", mode="append", body="Org review guidance.")
    composed = await composition.compose_playbook_intent(
        repository_uid="repo-1",
        playbook="review",
        stage="review",
        repo_guidance="Repo review guidance body.",
        structural="Review pull request #7 and finish with a verdict.",
        org_uid="org-a",
    )
    out = composed.text
    assert out.index("You are OpenSweep") < out.index("Seeded review instructions.")
    assert out.index("Seeded review instructions.") < out.index("## Organization guidance")
    assert out.index("## Organization guidance") < out.index("Repo review guidance body.")
    assert out.index("Repo review guidance body.") < out.index("Review pull request #7")
    assert out.index("Review pull request #7") < out.index("# Look-before-write contract")
    # Provenance for the Run row (recorded at dispatch by trigger_run).
    assert composed.overlay_uid == _OVERLAYS[0].uid
    assert composed.overlay_rev == 1


async def test_compose_replace_keeps_repo_guidance_and_structural(monkeypatch):
    from domains.agent_overlays.services import composition

    async def fake_base(playbook):
        return "Seeded fix instructions."

    monkeypatch.setattr(composition, "_resolve_platform_base", fake_base)
    await _put(playbook="fix", mode="replace", body="Org replacement instructions.")
    composed = await composition.compose_playbook_intent(
        repository_uid="repo-1",
        playbook="fix",
        stage="fix",
        repo_guidance="Repo fix guidance body.",
        structural="Fix the blocking findings on PR #9.",
        org_uid="org-a",
    )
    out = composed.text
    assert "Org replacement instructions." in out
    assert "Seeded fix instructions." not in out
    assert "Repo fix guidance body." in out  # replace never removes repo guidance
    assert "Fix the blocking findings on PR #9." in out  # …or the structural contract
    assert "# Look-before-write contract" in out  # …or the footer


async def test_compose_degrades_when_every_layer_is_broken(monkeypatch):
    """No org, no base row, broken overlay store — the run still gets a
    usable intent from the in-code fallback."""
    from domains.agent_overlays.services import composition

    async def broken_base(playbook):
        return None

    class Broken:
        class nodes:
            @staticmethod
            async def filter(**kw):
                raise RuntimeError("db down")

    monkeypatch.setattr(composition, "_resolve_platform_base", broken_base)
    monkeypatch.setattr(svc, "OrgAgentOverlay", Broken)
    composed = await composition.compose_playbook_intent(
        repository_uid="repo-1",
        playbook="verify",
        stage="verify",
        repo_guidance="",
        structural="Verify finding X.",
        org_uid="org-a",
    )
    from domains.agent_prompts.services.seed_agent_bases import agent_base_fallback

    assert agent_base_fallback("verify") in composed.text
    assert "Verify finding X." in composed.text
    assert composed.overlay_uid == "" and composed.overlay_rev == 0


async def test_chat_layers_have_no_header_or_footer(monkeypatch):
    from domains.agent_overlays.services import composition

    async def fake_base(playbook):
        return "Platform chat instructions."

    monkeypatch.setattr(composition, "_resolve_platform_base", fake_base)
    await _put(playbook="chat", mode="append", body="Org chat guidance.")
    layers = await composition.chat_instruction_layers("org-a")
    assert "Platform chat instructions." in layers
    assert "## Organization guidance" in layers
    assert "Org chat guidance." in layers
    assert "You are OpenSweep, an agent analyzing" not in layers  # no framing header
    assert "# Look-before-write contract" not in layers  # no footer
