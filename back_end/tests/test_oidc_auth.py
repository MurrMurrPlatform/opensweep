"""Zitadel OIDC layer — JWT verification in TokenAuthMiddleware + role mapping.

Runs against a mini app (no DB): the endpoint echoes what the middleware
stashed in scope["state"], so these tests assert the auth decision and the
claims handoff, not the User upsert (which needs Neo4j).

The JWKS cache in infrastructure.oidc is seeded directly with a generated
RSA key — no network.
"""

import json
import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jwt import PyJWK

import infrastructure.oidc as oidc
from app import TokenAuthMiddleware
from config import settings
from infrastructure.oidc import map_opensweep_role, primary_org_id, zitadel_roles

ISSUER = "https://auth.test"
CLIENT_ID = "spa-client-id"
KID = "test-kid"
SHARED = "shared-sekrit"

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_PEM = _PRIVATE_KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)


def _seed_jwks(monkeypatch):
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_PRIVATE_KEY.public_key()))
    jwk.update({"kid": KID, "alg": "RS256", "use": "sig"})
    monkeypatch.setattr(oidc, "_keys", {KID: PyJWK(jwk)})
    # Recent fetch — unknown kids fail fast instead of hitting the network.
    monkeypatch.setattr(oidc, "_last_fetch", time.monotonic())


def make_token(**overrides) -> str:
    claims = {
        "iss": ISSUER,
        "sub": "zitadel-user-1",
        "aud": [CLIENT_ID, "some-project-id"],
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "iat": datetime.now(UTC),
        "urn:zitadel:iam:org:project:roles": {"maintainer": {"org1": "org1.test"}},
    }
    claims.update(overrides)
    headers = {"kid": overrides.pop("_kid", KID)}
    return jwt.encode(claims, _PRIVATE_PEM, algorithm="RS256", headers=headers)


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "OPENSWEEP_AUTH_TOKEN", SHARED)
    monkeypatch.setattr(settings, "ZITADEL_ISSUER", ISSUER)
    monkeypatch.setattr(settings, "ZITADEL_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(settings, "ZITADEL_PROJECT_ID", "")
    _seed_jwks(monkeypatch)

    mini = FastAPI()

    @mini.get("/api/v1/whoami")
    async def whoami(request: Request):
        state = request.scope.get("state") or {}
        claims = state.get("oidc_claims")
        return {"sub": claims.get("sub") if claims else None}

    mini.add_middleware(TokenAuthMiddleware)
    return TestClient(mini)


def _get(client, token):
    return client.get("/api/v1/whoami", headers={"Authorization": f"Bearer {token}"})


# ── Middleware decisions ─────────────────────────────────────────────────────


def test_valid_jwt_accepted_and_claims_stashed(client):
    res = _get(client, make_token())
    assert res.status_code == 200
    assert res.json() == {"sub": "zitadel-user-1"}


def test_shared_token_still_works_without_claims(client):
    res = _get(client, SHARED)
    assert res.status_code == 200
    assert res.json() == {"sub": None}


def test_expired_jwt_rejected(client):
    res = _get(client, make_token(exp=datetime.now(UTC) - timedelta(minutes=1)))
    assert res.status_code == 401


def test_wrong_issuer_rejected(client):
    assert _get(client, make_token(iss="https://evil.test")).status_code == 401


def test_wrong_audience_rejected(client):
    assert _get(client, make_token(aud=["other-client"])).status_code == 401


def test_unknown_kid_rejected_without_refetch(client):
    assert _get(client, make_token(_kid="nope")).status_code == 401


def test_garbage_token_rejected(client):
    assert _get(client, "not-a-jwt-at-all").status_code == 401


def test_oidc_only_mode_enforces_auth(monkeypatch):
    """ZITADEL_ISSUER alone (no shared token) must still gate requests."""
    monkeypatch.setattr(settings, "OPENSWEEP_AUTH_TOKEN", "")
    monkeypatch.setattr(settings, "ZITADEL_ISSUER", ISSUER)
    monkeypatch.setattr(settings, "ZITADEL_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(settings, "ZITADEL_PROJECT_ID", "")
    _seed_jwks(monkeypatch)

    mini = FastAPI()

    @mini.get("/api/v1/thing")
    async def thing():
        return {"ok": True}

    mini.add_middleware(TokenAuthMiddleware)
    c = TestClient(mini)

    assert c.get("/api/v1/thing").status_code == 401
    res = c.get("/api/v1/thing", headers={"Authorization": f"Bearer {make_token()}"})
    assert res.status_code == 200


def test_audience_accepts_project_id(client, monkeypatch):
    monkeypatch.setattr(settings, "ZITADEL_CLIENT_ID", "different-spa")
    monkeypatch.setattr(settings, "ZITADEL_PROJECT_ID", "some-project-id")
    assert _get(client, make_token()).status_code == 200


# ── Claim mapping ────────────────────────────────────────────────────────────


def test_role_mapping_takes_highest():
    claims = {
        "urn:zitadel:iam:org:project:roles": {"viewer": {}, "admin": {}},
    }
    assert map_opensweep_role(claims) == "admin"


def test_role_mapping_project_scoped_claim():
    claims = {"urn:zitadel:iam:org:project:123456:roles": {"maintainer": {}}}
    assert zitadel_roles(claims) == {"maintainer"}
    assert map_opensweep_role(claims) == "maintainer"


def test_role_mapping_defaults_to_viewer():
    assert map_opensweep_role({}) == "viewer"
    assert map_opensweep_role({"urn:zitadel:iam:org:project:roles": {"weird": {}}}) == "viewer"


def test_primary_org_id():
    assert primary_org_id({"urn:zitadel:iam:user:resourceowner:id": "314"}) == "314"
    assert primary_org_id({}) == ""
