"""Org management surface — owner/platform-admin gates, invitation rules,
and the org-bound GitHub install state. DB-free."""

import time

import pytest
from fastapi import HTTPException

from api.dependencies import require_org_owner, require_platform_admin
from api.v1.github_app import (
    mint_install_state,
    verify_install_state,
)
from domains.organizations.services.provisioning import personal_org_name
from domains.users.schemas import UserDTO
from domains.users.services.local_user import get_local_user

pytestmark = pytest.mark.asyncio


def _user(**kw) -> UserDTO:
    base = dict(
        uid="u1",
        email="a@b.c",
        display_name="A",
        role="admin",
        org_uid="org-a",
        org_role="member",
        is_platform_admin=False,
    )
    base.update(kw)
    return UserDTO(**base)


# ── Dependencies ─────────────────────────────────────────────────────────────


async def test_require_org_owner():
    owner = _user(org_role="owner")
    assert require_org_owner(owner) is owner
    with pytest.raises(HTTPException) as exc:
        require_org_owner(_user(org_role="member"))
    assert exc.value.status_code == 403


async def test_require_platform_admin_ignores_org_role():
    # An org admin/owner is NOT the instance operator.
    with pytest.raises(HTTPException) as exc:
        require_platform_admin(_user(role="admin", org_role="owner"))
    assert exc.value.status_code == 403
    operator = _user(is_platform_admin=True)
    assert require_platform_admin(operator) is operator


async def test_local_user_is_operator_and_owner():
    local = get_local_user()
    assert local.is_platform_admin is True
    assert local.org_role == "owner"
    assert local.onboarded is True


# ── Install state (installation → org binding) ──────────────────────────────


async def test_install_state_roundtrip_carries_org():
    state = mint_install_state("org-42")
    assert state.startswith("kis_")
    assert verify_install_state(state) == "org-42"


async def test_install_state_rejects_tampered_org():
    state = mint_install_state("org-42")
    prefix, rest = state.split("_", 1)
    ts, org, nonce, sig = rest.split(".")
    forged = f"{prefix}_{ts}.org-other.{nonce}.{sig}"
    assert verify_install_state(forged) == ""


async def test_install_state_expires():
    state = mint_install_state("org-42", now=int(time.time()) - 3601)
    assert verify_install_state(state) == ""


async def test_install_state_rejects_garbage():
    assert verify_install_state("") == ""
    assert verify_install_state("kis_not.a.state") == ""
    assert verify_install_state("kas_1.2.3") == ""


# ── Provisioning helpers ─────────────────────────────────────────────────────


async def test_personal_org_name():
    assert personal_org_name("Ada Lovelace", "ada@x.io") == "Ada Lovelace's organization"
    assert personal_org_name("", "ada@x.io") == "ada's organization"
    assert personal_org_name("", "") == "My organization"


async def test_userdto_defaults_are_safe():
    """Old call sites that don't pass the new fields must not become
    accidentally privileged."""
    dto = UserDTO(uid="u", email="e@x.y", display_name="U", org_uid="o")
    assert dto.is_platform_admin is False
    assert dto.org_role == "member"
    assert dto.onboarded is True
