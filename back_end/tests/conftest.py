"""Pytest fixtures.

Most tests are pure-Python (policy engine, state-machine guards). They do not
require Neo4j. Integration tests that need the DB are skipped unless
NEO4J_HOST is reachable.
"""

import os
import socket

import pytest


def _neo4j_reachable() -> bool:
    host = os.environ.get("NEO4J_HOST", "opensweep_neo4j")
    port = int(os.environ.get("NEO4J_PORT", 7687))
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def neo4j_available() -> bool:
    return _neo4j_reachable()
