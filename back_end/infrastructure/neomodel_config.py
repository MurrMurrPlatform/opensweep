"""Neomodel driver configuration."""

from neomodel import config as neomodel_conf

from config import settings


def configure_neomodel() -> None:
    """Point neomodel at the configured Neo4j instance (sync driver)."""
    neomodel_conf.DATABASE_URL = settings.NEO4J_BOLT_URL
