"""
Conprehensive test configuration for Minder services.
Provides fixtures and utilities for unit, integration, and E2E tests.
"""

import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    # Add project root to path for imports
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

    # Import from services with correct module names
    def load_service_module(service_path, module_name=None):
        """Load service module dynamically"""
        if module_name is None:
            module_name = service_path.name.replace("-", "_")

        # Add service directory to sys.path for relative imports
        sys.path.insert(0, str(service_path))

        spec = importlib.util.spec_from_file_location(module_name, service_path / "main.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    services_base = project_root / "services"

    # Load services individually to avoid one failure blocking all
    gateway_app = None
    registry_app = None
    marketplace_app = None
    rag_app = None
    model_app = None
    tts_app = None

    try:
        gateway_app = load_service_module(services_base / "api-gateway", "api_gateway.main")
        print("✅ Loaded API Gateway")
    except Exception as e:
        print(f"❌ Failed to load API Gateway: {e}")

    try:
        registry_app = load_service_module(services_base / "plugin-registry", "plugin_registry.main")
        print("✅ Loaded Plugin Registry")
    except Exception as e:
        print(f"❌ Failed to load Plugin Registry: {e}")

    try:
        marketplace_app = load_service_module(services_base / "marketplace", "marketplace.main")
        print("✅ Loaded Marketplace")
    except Exception as e:
        print(f"❌ Failed to load Marketplace: {e}")

    try:
        rag_app = load_service_module(services_base / "rag-pipeline", "rag_pipeline.main")
        print("✅ Loaded RAG Pipeline")
    except Exception as e:
        print(f"❌ Failed to load RAG Pipeline: {e}")

    try:
        model_app = load_service_module(services_base / "model-management", "model_management.main")
        print("✅ Loaded Model Management")
    except Exception as e:
        print(f"❌ Failed to load Model Management: {e}")

    try:
        tts_app = load_service_module(services_base / "tts-stt-service", "tts_stt_service.main")
        print("✅ Loaded TTS-STT Service")
    except Exception as e:
        print(f"❌ Failed to load TTS-STT Service: {e}")

except Exception as e:
    # Catch any unexpected errors
    print(f"Warning: Unexpected error loading service modules: {e}")


# Test configuration
pytest_plugins = ("pytest_asyncio",)


# Database fixtures
@pytest.fixture(scope="session")
def test_database_url():
    """Get test database URL"""
    return os.getenv("TEST_DATABASE_URL", "postgresql://test:test@localhost:5432/minder_test")


@pytest_asyncio.fixture(scope="function")
async def test_db_pool(test_database_url):
    """Create test database connection pool"""
    pool = await asyncpg.create_pool(test_database_url, min_size=1, max_size=5, command_timeout=60)

    yield pool

    # Cleanup
    await pool.close()


@pytest_asyncio.fixture(scope="function")
async def test_db_connection(test_db_pool):
    """Get test database connection"""
    async with test_db_pool.acquire() as conn:
        yield conn


@pytest_asyncio.fixture(scope="function")
async def clean_test_db(test_db_pool):
    """Clean test database before/after tests"""
    # Clean up
    async with test_db_pool.acquire() as conn:
        await conn.execute("DROP SCHEMA IF EXISTS test CASCADE")
        await conn.execute("CREATE SCHEMA test")

    yield

    # Cleanup
    async with test_db_pool.acquire() as conn:
        await conn.execute("DROP SCHEMA IF EXISTS test CASCADE")


# Redis fixtures
@pytest.fixture(scope="session")
def redis_url():
    """Get test Redis URL"""
    return os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")


@pytest.fixture(scope="function")
def redis_client(redis_url):
    """Create Redis client for tests"""
    try:
        import redis

        return redis.from_url(redis_url, decode_responses=True, socket_timeout=5, socket_connect_timeout=5)
    except Exception as e:
        print(f"Warning: Redis client not available: {e}")
        return None


@pytest.fixture(scope="function")
def redis_client_mock():
    """Mock Redis client for integration tests (avoid DNS issues)"""
    mock_client = MagicMock()
    mock_client.get.return_value = None
    mock_client.set.return_value = True
    mock_client.delete.return_value = True
    mock_client.exists.return_value = False
    mock_client.pipeline.return_value = MagicMock()

    return mock_client


# Auto-use fixture to mock Redis globally for integration tests
@pytest.fixture(scope="session", autouse=True)
def patch_redis_globally():
    """Auto-use fixture to patch Redis globally for integration tests"""
    # Create mock Redis client
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = True
    mock_redis.exists.return_value = False
    mock_redis.pipeline.return_value = MagicMock()
    mock_redis.close.return_value = None

    # Patch Redis globally to avoid DNS issues
    with patch('redis.from_url', return_value=mock_redis):
        yield


@pytest.fixture(scope="function")
def mock_redis_pipeline():
    """Mock Redis pipeline for tests"""

    def create_mock_pipeline(zcard_result=0):
        """Helper to create a properly configured mock pipeline"""
        mock_pipeline = AsyncMock()
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)
        mock_pipeline.zremrangebyscore = AsyncMock(return_value=0)
        mock_pipeline.zcard = AsyncMock(return_value=zcard_result)
        mock_pipeline.zadd = AsyncMock(return_value=1)
        mock_pipeline.expire = AsyncMock(return_value=True)
        mock_pipeline.execute = AsyncMock(return_value=[0, zcard_result, 1, True])
        return mock_pipeline

    return create_mock_pipeline


@pytest_asyncio.fixture(scope="function")
async def test_redis(redis_url):
    """Create test Redis client"""
    redis = Redis.from_url(redis_url, decode_responses=True)

    # Ensure we're using a test database
    await redis.flushdb()

    yield redis

    # Cleanup
    await redis.flushdb()
    await redis.close()


# HTTP client fixtures
@pytest.fixture(scope="function")
async def test_client():
    """Create test HTTP client"""
    transport = ASGITransport(app=gateway_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(scope="function")
def gateway_test_client():
    """Create gateway test client"""
    # Access to FastAPI app from the module
    return TestClient(gateway_app.app) if gateway_app else TestClient(None)


# Auth fixtures
@pytest.fixture(scope="function")
def test_token():
    """Get test JWT token"""
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"


@pytest.fixture(scope="function")
def test_headers(test_token):
    """Get test headers with auth token"""
    return {"Authorization": f"Bearer {test_token}"}


# Mock fixtures
@pytest.fixture(scope="function")
def mock_postgres_pool():
    """Mock PostgreSQL pool"""
    pool = AsyncMock(spec=asyncpg.Pool)
    pool.acquire.return_value.__aenter__.return_value = AsyncMock()
    return pool


@pytest.fixture(scope="function")
def mock_redis():
    """Mock Redis"""
    return AsyncMock()


@pytest.fixture(scope="function")
def mock_redis_client():
    """Mock Redis client"""
    return AsyncMock()


@pytest.fixture(scope="function")
def mock_redis_client_with_pipeline():
    """Mock Redis client with properly configured pipeline"""

    from unittest.mock import AsyncMock, Mock

    def create_mock_pipeline(zcard_result=0):
        """Helper to create a properly configured mock pipeline"""
        mock_pipeline = Mock()
        mock_pipeline.zremrangebyscore = Mock(return_value=0)
        mock_pipeline.zcard = Mock(return_value=zcard_result)
        mock_pipeline.zadd = Mock(return_value=1)
        mock_pipeline.expire = Mock(return_value=True)
        mock_pipeline.execute = Mock(return_value=[0, zcard_result, 1, True])
        return mock_pipeline

    redis = AsyncMock(spec=Redis)
    redis.pipeline = Mock(return_value=create_mock_pipeline(0))
    return redis


@pytest.fixture(scope="function")
def mock_http_client():
    """Mock HTTP client"""
    return AsyncMock()


@pytest.fixture(scope="function")
def mock_neo4j_driver():
    """Mock Neo4j driver"""
    return AsyncMock()


# Test data fixtures
@pytest.fixture(scope="function")
def sample_plugin_data():
    """Sample plugin data"""
    return {
        "name": "test-plugin",
        "version": "1.0.0",
        "description": "Test plugin",
        "author": "Test Author",
        "license": "MIT",
        "repository": "https://github.com/test/test-plugin",
    }


@pytest.fixture(scope="function")
def sample_user_data():
    """Sample user data"""
    return {"username": "testuser", "email": "test@example.com", "password": "TestPassword123!"}


@pytest.fixture(scope="function")
def sample_plugin_manifest():
    """Sample plugin manifest"""
    return {
        "name": "test-plugin",
        "version": "1.0.0",
        "description": "Test plugin description",
        "author": {"name": "Test Author", "email": "test@example.com"},
        "license": "MIT",
        "repository": "https://github.com/test/test-plugin",
        "dependencies": [],
        "capabilities": ["data_collection", "ai_tools"],
        "configuration": {"database": {"schema": "test_plugin"}, "api": {"base_url": "http://localhost:8001"}},
    }


@pytest.fixture(scope="function")
def sample_rag_query():
    """Sample RAG query"""
    return {"query": "What is the purpose of this plugin?", "context": ["plugin context"], "max_results": 5}


@pytest.fixture(scope="function")
def sample_tts_request():
    """Sample TTS request"""
    return {"text": "Hello, this is a test", "language": "en", "voice": "default"}


# Test utilities
@pytest.fixture(scope="function")
def assert_response():
    """Utility for asserting HTTP responses"""

    def _assert(response, status_code: int = None, has_error: bool = False, error_code: str = None):
        if status_code is not None:
            assert response.status_code == status_code, f"Expected status {status_code}, got {response.status_code}"

        if has_error:
            assert "error" in response.json() or "detail" in response.json(), "Expected error in response"

            if error_code:
                json_response = response.json()
                error_obj = json_response.get("error", json_response)
                assert (
                    error_obj.get("code") == error_code or json_response.get("detail") == error_code
                ), f"Expected error code {error_code}"

    return _assert


# API Gateway specific fixtures
@pytest.fixture(scope="function")
def gateway_test_client_no_redis():
    """Create test client without Redis dependency (for testing without rate limiting)"""
    # Access to FastAPI app from the module
    if gateway_app:
        with unittest.mock.patch("services.api-gateway.main.redis_client", return_value=None):
            return TestClient(gateway_app.app)
    else:
        return TestClient(None)


# E2E test specific fixtures
@pytest.fixture(scope="session")
def e2e_test_env():
    """E2E test environment variables"""
    return {
        "TEST_REDIS_URL": "redis://localhost:6379/15",
        "TEST_DATABASE_URL": "postgresql://test:test@localhost:5432/minder_test",
        "JWT_SECRET": "test-secret-for-jwt-tokens",
        "ENVIRONMENT": "test",
    }


@pytest.fixture(scope="session")
def e2e_test_users():
    """E2E test users"""
    return {
        "test_user": {
            "username": "testuser",
            "password": "testpass123",
            "email": "test@example.com",
        },
        "test_admin": {
            "username": "admin",
            "password": "adminpass123",
            "email": "admin@example.com",
        },
    }


# Plugin test fixtures
@pytest.fixture(scope="function")
def mock_plugin_registry():
    """Mock plugin registry"""
    registry = AsyncMock()
    registry.get_all_plugins = AsyncMock(return_value=[])
    registry.get_plugin = AsyncMock(return_value=None)
    registry.register_plugin = AsyncMock(return_value=True)
    registry.unregister_plugin = AsyncMock(return_value=True)
    return registry


@pytest.fixture(scope="function")
def sample_plugin_list():
    """Sample plugin list"""
    return [
        {
            "name": "tefas",
            "version": "1.0.0",
            "description": "Türkiye yatırım fonları analizi (borsapy 0.8.7 + tefas-crawler integrated)",
            "author": "Minder",
            "status": "enabled",
            "enabled": True,
            "dependencies": [],
            "capabilities": ["fund_data_collection", "historical_analysis", "fund_discovery", "kap_integration", "risk_metrics", "tax_rates", "fund_comparison", "technical_analysis", "fund_screening"],
            "data_sources": ["TEFAS (via tefas-crawler)", "TEFAS (via borsapy 0.8.7)", "KAP"],
            "databases": ["postgresql", "influxdb"],
            "registered_at": "2026-05-01T06:41:40.555350",
            "health_status": "healthy",
            "last_health_check": "2026-05-01T09:07:23.594303"
        },
        {
            "name": "weather",
            "version": "1.0.0",
            "description": "Weather data aggregation and analysis",
            "author": "Minder",
            "status": "enabled",
            "enabled": True,
            "dependencies": [],
            "capabilities": ["weather_data_collection", "forecast_analysis", "seasonal_pattern_detection"],
            "data_sources": ["Open-Meteo API"],
            "databases": ["postgresql", "influxdb"],
            "registered_at": "2026-05-01T06:41:37.654885",
            "health_status": "healthy",
            "last_health_check": "2026-05-01T09:07:23.559549"
        },
    ]
