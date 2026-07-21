"""Pytest fixtures.

Most tests are pure-Python (policy engine, state-machine guards). They do not
require Neo4j. Integration tests that need the DB are skipped unless the
dedicated *test* Neo4j is reachable.

## Integration harness (Phase 5)

A small set of P0/P1 integration tests run against a dedicated, ISOLATED test
Neo4j (never the dev DB): bolt://localhost:7999. The harness:

- `test_db` (session-scoped, autouse): points neomodel at 7999, installs the
  async connection, and creates constraints once. If 7999 is unreachable it
  yields None and every integration test SKIPS cleanly (DB-less CI still
  passes).
- `clean_db` (function-scoped, autouse for `@pytest.mark.integration` tests):
  wipes the test graph between tests. Guarded so it can ONLY run against a
  connection URL containing ":7999" — it will refuse to touch anything else.

Integration tests opt in with `@pytest.mark.integration`; the autouse
`_require_test_db` fixture skips them when the DB is absent.
"""

import os
import socket

import pytest

# The dedicated, isolated test Neo4j. NEVER the dev DB (7688) — that holds the
# user's real data. Overridable via env only to a *test* instance.
TEST_NEO4J_HOST = os.environ.get("TEST_NEO4J_HOST", "localhost")
TEST_NEO4J_PORT = int(os.environ.get("TEST_NEO4J_PORT", 7999))
TEST_NEO4J_USER = os.environ.get("TEST_NEO4J_USER", "neo4j")
TEST_NEO4J_PASSWORD = os.environ.get("TEST_NEO4J_PASSWORD", "testpassword123")
TEST_NEO4J_URL = (
    f"bolt://{TEST_NEO4J_USER}:{TEST_NEO4J_PASSWORD}@{TEST_NEO4J_HOST}:{TEST_NEO4J_PORT}"
)

# Absolute safety: destructive whole-graph wipes are only ever allowed against
# a connection whose URL carries this port. Any drift away from the dedicated
# test instance disarms the wipe.
_SAFE_WIPE_PORT_MARKER = ":7999"


def _neo4j_reachable() -> bool:
    host = os.environ.get("NEO4J_HOST", "opensweep_neo4j")
    port = int(os.environ.get("NEO4J_PORT", 7687))
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _test_db_reachable() -> bool:
    try:
        with socket.create_connection((TEST_NEO4J_HOST, TEST_NEO4J_PORT), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def neo4j_available() -> bool:
    return _neo4j_reachable()


def _register_integration_marker(config):
    config.addinivalue_line(
        "markers",
        "integration: test requires the dedicated test Neo4j (localhost:7999); "
        "skipped when unreachable.",
    )


def pytest_configure(config):
    _register_integration_marker(config)


@pytest.fixture(scope="session")
def test_db() -> str | None:
    """Point neomodel at the dedicated test Neo4j (localhost:7999). SYNChronous
    so it resolves outside any test event loop; the async connection + one-time
    constraint creation happen per-test in `_require_test_db` (which runs in the
    test's own loop). Returns the connection URL, or None when the DB is
    unreachable (integration tests then skip)."""
    if not _test_db_reachable():
        return None
    from neomodel import config as neomodel_conf

    # Mirror app.py's configure_neomodel(), but pinned at the TEST instance.
    neomodel_conf.DATABASE_URL = TEST_NEO4J_URL
    return TEST_NEO4J_URL


# One-time constraint creation, done lazily inside the first integration test's
# loop (create_constraints is async and idempotent).
_constraints_ready = False


async def _ensure_connection_and_constraints() -> None:
    global _constraints_ready
    from neomodel import adb
    from neomodel import config as neomodel_conf

    neomodel_conf.DATABASE_URL = TEST_NEO4J_URL
    # Bind the async driver to THIS loop. neomodel caches per-URL, but a stale
    # driver from a closed loop must be replaced — set_connection is idempotent
    # and cheap, so we (re)install every test.
    await adb.set_connection(url=TEST_NEO4J_URL)
    if not _constraints_ready:
        from infrastructure.neomodel_bootstrap import create_constraints

        await create_constraints()
        _constraints_ready = True


async def _wipe_test_graph() -> None:
    """DETACH DELETE the whole test graph. GUARDED: refuses unless the live
    neomodel connection URL targets the dedicated test port (:7999)."""
    from neomodel import adb
    from neomodel import config as neomodel_conf

    url = getattr(neomodel_conf, "DATABASE_URL", "") or ""
    if _SAFE_WIPE_PORT_MARKER not in url:
        raise RuntimeError(
            f"refusing to wipe: connection URL {url!r} is not the dedicated "
            f"test instance ({_SAFE_WIPE_PORT_MARKER})"
        )
    await adb.cypher_query("MATCH (n) DETACH DELETE n")


@pytest.fixture(autouse=True)
async def _require_test_db(request):
    """For tests marked `integration`: skip when the test DB is absent, else
    install the async connection and wipe the graph before/after so every test
    starts from a clean slate."""
    if request.node.get_closest_marker("integration") is None:
        yield
        return

    db_url = request.getfixturevalue("test_db")
    if db_url is None:
        pytest.skip("dedicated test Neo4j (localhost:7999) not reachable")

    await _ensure_connection_and_constraints()
    await _wipe_test_graph()
    yield
    await _wipe_test_graph()
