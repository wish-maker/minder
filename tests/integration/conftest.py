"""
Integration test configuration
Sets up test environment BEFORE any app code is imported
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

# Test environment - MUST match docker/docker-compose.test.yml
# IMPORTANT: Set env vars BEFORE importing any app code
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")  # local default; CI sets via env
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "testpass")  # local default; CI sets via env
os.environ.setdefault("POSTGRES_DB", "minder_test")
# DB_* mirrors POSTGRES_* (#265): api-gateway's Settings (MinderBaseSettings) reads
# DB_HOST/PORT/USER/PASSWORD/NAME instead of the legacy POSTGRES_* names.
os.environ.setdefault("DB_HOST", os.environ["POSTGRES_HOST"])
os.environ.setdefault("DB_PORT", os.environ["POSTGRES_PORT"])
os.environ.setdefault("DB_USER", os.environ["POSTGRES_USER"])
os.environ.setdefault("DB_PASSWORD", os.environ["POSTGRES_PASSWORD"])
os.environ.setdefault("DB_NAME", os.environ["POSTGRES_DB"])
os.environ.setdefault("JWT_SECRET", "test_jwt_secret_for_e2e_tests")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRATION_MINUTES", "60")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
# was an unconditional `os.environ[...] = "testpass"` -- silently
# overriding CI's real Redis service-container password (ci.yml sets
# REDIS_PASSWORD=test_password) with a value that doesn't match it. Any test
# making a genuinely-authenticated real Redis connection (not the
# patch_redis_globally mock, which only intercepts redis.from_url) would
# fail to auth against CI's actual container -- confirmed live via a new
# rate-limiting test that needs a real Redis connection to clear its counter.
os.environ.setdefault("REDIS_PASSWORD", "testpass")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("MINDER_PHASE", "1")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

# Add api-gateway to path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../src/services/api-gateway")
)

# Import config - it should now read from os.environ
from config import settings  # noqa: E402

# Override directly to ensure test values (respect env for CI compatibility)
settings.DB_HOST = os.getenv("DB_HOST", "localhost")
settings.DB_PORT = int(os.getenv("DB_PORT", "5433"))
settings.DB_USER = os.getenv("DB_USER", "postgres")
settings.DB_PASSWORD = os.getenv("DB_PASSWORD", "testpass")
settings.DB_NAME = os.getenv("DB_NAME", "minder_test")


@pytest.fixture(scope="session")
def marketplace_schema_ready(marketplace_app_isolated):
    """Ensure marketplace's real migrations (schema.sql, idempotent -- safe to
    run more than once) have actually run against the real test DB before any
    raw-asyncpg schema-introspection test connects (#333). Migrations only
    run inside the app's lifespan (main.py's `from migrations import
    run_migrations` is a deferred, function-body import), triggered here via
    TestClient's context-manager __enter__/__exit__."""
    with TestClient(marketplace_app_isolated.app):
        pass
