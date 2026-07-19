"""
Integration test configuration
Sets up test environment BEFORE any app code is imported
"""

import os
import sys

# Test environment - MUST match docker-compose.test.yml
# IMPORTANT: Set env vars BEFORE importing any app code
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")  # local default; CI sets via env
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "testpass")  # local default; CI sets via env
os.environ.setdefault("POSTGRES_DB", "minder_test")
os.environ["JWT_SECRET"] = "test_jwt_secret_for_e2e_tests"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_EXPIRATION_MINUTES"] = "60"
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6379"
os.environ["REDIS_PASSWORD"] = "testpass"
os.environ["LOG_LEVEL"] = "INFO"
os.environ["ENVIRONMENT"] = "test"
os.environ["MINDER_PHASE"] = "1"
os.environ["RATE_LIMIT_ENABLED"] = "false"

# Add api-gateway to path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../src/services/api-gateway")
)

# Import config - it should now read from os.environ
from config import settings  # noqa: E402

# Override directly to ensure test values (respect env for CI compatibility)
settings.POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
settings.POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5433"))
settings.POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
settings.POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "testpass")
settings.POSTGRES_DB = os.getenv("POSTGRES_DB", "minder_test")
