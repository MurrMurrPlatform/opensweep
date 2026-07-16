"""Throwaway smoke test: tenancy migration against a real Neo4j.

Simulates BOTH deployment shapes and runs each twice (first + second deploy):
  A) fresh instance — empty graph, migration must be a clean no-op that only
     seeds the local org;
  B) phase-2 upgrade — users with idp_org_id but no org_uid, repos with
     org_uid + github_installation_id, no Organization/ownership — migration
     must stamp membership, promote owners, mint org nodes, link installs.

Run: NEO4J_BOLT=bolt://neo4j:testpassword@localhost:7699 python -m scripts.smoke_migration
"""

import asyncio
import os

from neomodel import adb


async def q(cy, **params):
    rows, _ = await adb.cypher_query(cy, params)
    return rows


async def check(label, cond):
    print(("  ok  " if cond else "  FAIL") + f" {label}")
    if not cond:
        raise SystemExit(1)


async def main():
    await adb.set_connection(url=os.environ["NEO4J_BOLT"])

    from domains.organizations.services.provisioning import migrate_tenancy
    from infrastructure.neomodel_bootstrap import create_constraints

    # ── A) fresh instance ────────────────────────────────────────────────────
    print("A) fresh instance")
    await q("MATCH (n) DETACH DELETE n")
    await create_constraints()
    await migrate_tenancy()  # first deploy
    await migrate_tenancy()  # second deploy
    orgs = await q("MATCH (o:Organization) RETURN o.uid, o.name")
    await check("only the local org exists", [r[0] for r in orgs] == ["local-org"])

    # ── B) phase-2 upgrade ───────────────────────────────────────────────────
    print("B) phase-2 upgrade graph")
    await q("MATCH (n) DETACH DELETE n")
    await q(
        """
        CREATE (:User {uid:'u-admin', email:'a@x.io', display_name:'Admin',
                       role:'admin', idp_org_id:'zorg-1', created_at: datetime('2026-01-01T00:00:00Z')}),
               (:User {uid:'u-view', email:'v@x.io', display_name:'Viewer',
                       role:'viewer', idp_org_id:'zorg-1', created_at: datetime('2026-01-02T00:00:00Z')}),
               (:User {uid:'u-lone', email:'l@x.io', display_name:'Lone',
                       role:'viewer', idp_org_id:'zorg-2', created_at: datetime('2026-01-03T00:00:00Z')}),
               (:Repository {uid:'r1', slug:'one', name:'one', org_uid:'zorg-1',
                             github_installation_id: 111}),
               (:Repository {uid:'r2', slug:'two', name:'two', org_uid:'zorg-2',
                             github_installation_id: 222})
        """
    )
    await migrate_tenancy()  # first deploy after upgrade
    snapshot1 = {
        "users": await q(
            "MATCH (u:User) RETURN u.uid, u.org_uid, u.org_role, u.onboarded ORDER BY u.uid"
        ),
        "orgs": await q("MATCH (o:Organization) RETURN o.uid ORDER BY o.uid"),
        "links": await q(
            "MATCH (g:GitConnection) RETURN g.external_id, g.org_uid "
            "ORDER BY g.external_id"
        ),
    }
    await migrate_tenancy()  # second deploy — must change nothing
    snapshot2 = {
        "users": await q(
            "MATCH (u:User) RETURN u.uid, u.org_uid, u.org_role, u.onboarded ORDER BY u.uid"
        ),
        "orgs": await q("MATCH (o:Organization) RETURN o.uid ORDER BY o.uid"),
        "links": await q(
            "MATCH (g:GitConnection) RETURN g.external_id, g.org_uid "
            "ORDER BY g.external_id"
        ),
    }

    await check("idempotent (second run is a no-op)", snapshot1 == snapshot2)
    await check(
        "users stamped into their idp orgs",
        [(r[0], r[1]) for r in snapshot1["users"]]
        == [("u-admin", "zorg-1"), ("u-lone", "zorg-2"), ("u-view", "zorg-1")],
    )
    roles = {r[0]: r[2] for r in snapshot1["users"]}
    await check("pre-existing admin became owner", roles["u-admin"] == "owner")
    await check("viewer stayed member in shared org", roles["u-view"] == "member")
    await check("sole member of zorg-2 promoted to owner", roles["u-lone"] == "owner")
    await check("everyone marked onboarded", all(r[3] for r in snapshot1["users"]))
    await check(
        "org nodes minted for every org in use",
        [r[0] for r in snapshot1["orgs"]] == ["local-org", "zorg-1", "zorg-2"],
    )
    await check(
        "installations linked to their repos' orgs",
        [(int(r[0]), r[1]) for r in snapshot1["links"]] == [(111, "zorg-1"), (222, "zorg-2")],
    )
    print("all checks passed")


asyncio.run(main())
