"""
Integration test configuration
Sets up test environment BEFORE any app code is imported
"""

import os
import sys

# Test environment - MUST match docker-compose.test.yml
# IMPORTANT: Set env vars BEFORE importing any app code
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5433"
os.environ["POSTGRES_USER"] = "postgres"
os.environ["POSTGRES_PASSWORD"] = "testpass"
os.environ["POSTGRES_DB"] = "minder_test"
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
import config
from config import settings

# Override directly to ensure test values
settings.POSTGRES_HOST = "localhost"
settings.POSTGRES_PORT = 5433
settings.POSTGRES_USER = "postgres"
settings.POSTGRES_PASSWORD = "testpass"
settings.POSTGRES_DB = "minder_test"
