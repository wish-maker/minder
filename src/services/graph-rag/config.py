"""Centralized settings for the Graph RAG service.

Single source of truth for env config, replacing the ``os.getenv`` calls that were
previously inline in ``main.py``. This service talks only to Neo4j + spaCy (no
DB/Redis/JWT), so it uses a plain ``BaseSettings`` rather than
``shared.config.MinderBaseSettings`` (adopting the base would force the required
DB_PASSWORD/REDIS_PASSWORD/JWT_SECRET secrets it does not use — same rationale as
model-management). ``NEO4J_AUTH`` (format ``user/password``) is required and parsed
here, fail-fast on import.
"""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    NEO4J_URI: str = "bolt://neo4j:7687"
    SPACY_MODEL: str = "en_core_web_sm"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


def _neo4j_credentials() -> "tuple[str, str]":
    """Parse ``NEO4J_AUTH`` (``user/password``) → ``(user, password)``; fail-fast."""
    auth = os.getenv("NEO4J_AUTH")
    if not auth:
        raise ValueError(
            "NEO4J_AUTH must be set via environment variable (format: neo4j/password)"
        )
    if "/" in auth:
        user, password = auth.split("/", 1)
    else:
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")
    return user, password


NEO4J_USER, NEO4J_PASSWORD = _neo4j_credentials()
