"""
Comprehensive test configuration for Minder services.
Provides fixtures and utilities for unit, integration, and E2E tests.
"""

import asyncio
import importlib.util
import os
import sys

# Import FastAPI apps (optional, try-except for unit tests)
from pathlib import Path
from unittest.mock import AsyncMock

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

        spec = importlib.util.spec_from_file_location(module_name, service_path / "main.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    services_base = project_root / "services"
    gateway_app = load_service_module(services_base / "api-gateway", "services.api_gateway.main")
    registry_app = load_service_module(services_base / "plugin-registry", "services.plugin_registry.main")
    marketplace_app = load_service_module(services_base / "marketplace", "services.marketplace.main")
    rag_app = load_service_module(services_base / "rag-pipeline", "services.rag_pipeline.main")
    model_app = load_service_module(services_base / "model-management", "services.model_management.main")
    tts_app = load_service_module(services_base / "tts-stt-service", "services.tts_stt_service.main")
except Exception as e:
    # Services not available for unit tests
    print(f"Warning: Could not load service modules: {e}")
    gateway_app = None
    registry_app = None
    marketplace_app = None
    rag_app = None
    model_app = None
    tts_app = None


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
    return TestClient(gateway_app)


@pytest.fixture(scope="function")
def registry_test_client():
    """Create registry test client"""
    return TestClient(registry_app)


@pytest.fixture(scope="function")
def marketplace_test_client():
    """Create marketplace test client"""
    return TestClient(marketplace_app)


@pytest.fixture(scope="function")
def rag_test_client():
    """Create RAG test client"""
    return TestClient(rag_app)


@pytest.fixture(scope="function")
def model_test_client():
    """Create model management test client"""
    return TestClient(model_app)


@pytest.fixture(scope="function")
def tts_test_client():
    """Create TTS/STT test client"""
    return TestClient(tts_app)


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
def mock_redis_client():
    """Mock Redis client"""
    return AsyncMock(spec=Redis)


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


@pytest.fixture(scope="function")
def clean_redis_after(test_redis):
    """Clean Redis after test"""
    yield
    asyncio.run(test_redis.flushdb())


@pytest.fixture(scope="function")
def time_tracker():
    """Utility for tracking execution time"""
    import time

    times = {}

    def _track(name: str):
        times[name] = time.time()

    def _elapsed(name: str) -> float:
        return time.time() - times.get(name, 0)

    yield {"track": _track, "elapsed": _elapsed}


# Async test utilities
@pytest_asyncio.fixture(scope="function")
async def wait_for_condition(condition, timeout: float = 5.0, poll_interval: float = 0.1):
    """Wait for a condition to become true"""
    import time

    start = time.time()

    while time.time() - start < timeout:
        if await condition():
            return True
        await asyncio.sleep(poll_interval)

    raise TimeoutError(f"Condition not met within {timeout}s")


# Performance testing fixtures
@pytest.fixture(scope="function")
def performance_tracker():
    """Track performance metrics"""
    metrics = {"response_times": [], "memory_usage": [], "cpu_usage": []}

    def record_response_time(time_ms: float):
        metrics["response_times"].append(time_ms)

    def record_memory_usage(mb: float):
        metrics["memory_usage"].append(mb)

    def get_stats():
        import statistics

        if not metrics["response_times"]:
            return {}

        return {
            "avg_response_time": statistics.mean(metrics["response_times"]),
            "min_response_time": min(metrics["response_times"]),
            "max_response_time": max(metrics["response_times"]),
            "p95_response_time": (
                statistics.quantiles(metrics["response_times"], n=20)[18]
                if len(metrics["response_times"]) > 19
                else max(metrics["response_times"])
            ),
            "avg_memory": statistics.mean(metrics["memory_usage"]) if metrics["memory_usage"] else 0,
        }

    yield {"record_response": record_response_time, "record_memory": record_memory_usage, "get_stats": get_stats}


# Load testing fixtures
@pytest.fixture(scope="function")
async def load_tester():
    """Load testing utility"""

    async def run_load_test(
        endpoint: str,
        method: str = "GET",
        concurrent_users: int = 10,
        requests_per_user: int = 10,
        delay_between_requests: float = 0.1,
    ):
        """Run load test"""
        import time

        async def make_request(client, url):
            start = time.time()
            try:
                if method == "GET":
                    response = await client.get(url)
                else:
                    response = await client.post(url)
                elapsed = (time.time() - start) * 1000
                return {
                    "success": response.status_code < 400,
                    "status_code": response.status_code,
                    "response_time_ms": elapsed,
                }
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                return {"success": False, "error": str(e), "response_time_ms": elapsed}

        # Create test client
        from httpx import AsyncClient

        async with AsyncClient(base_url="http://test") as client:
            results = []
            total_requests = concurrent_users * requests_per_user

            for i in range(concurrent_users):
                for j in range(requests_per_user):
                    result = await make_request(client, endpoint)
                    results.append(result)

                    if delay_between_requests > 0:
                        await asyncio.sleep(delay_between_requests)

            # Calculate stats
            successful = [r for r in results if r["success"]]
            failed = [r for r in results if not r["success"]]

            if successful:
                response_times = [r["response_time_ms"] for r in successful]
                import statistics

                stats = {
                    "total_requests": total_requests,
                    "successful": len(successful),
                    "failed": len(failed),
                    "success_rate": len(successful) / total_requests * 100,
                    "avg_response_time_ms": statistics.mean(response_times),
                    "min_response_time_ms": min(response_times),
                    "max_response_time_ms": max(response_times),
                    "p95_response_time_ms": (
                        statistics.quantiles(response_times, n=20)[18]
                        if len(response_times) > 19
                        else max(response_times)
                    ),
                }
            else:
                stats = {
                    "total_requests": total_requests,
                    "successful": 0,
                    "failed": total_requests,
                    "success_rate": 0.0,
                }

            return stats

    return run_load_test


# Security testing fixtures
@pytest.fixture(scope="function")
async def security_tester():
    """Security testing utility"""

    async def test_sql_injection(test_client, endpoint: str, payloads: list):
        """Test SQL injection payloads"""
        results = []
        for payload in payloads:
            try:
                response = await test_client.get(f"{endpoint}?query={payload}")
                results.append(
                    {
                        "payload": payload,
                        "status_code": response.status_code,
                        "vulnerable": "syntax error" not in response.text.lower() and response.status_code != 500,
                    }
                )
            except Exception as e:
                results.append({"payload": payload, "error": str(e), "vulnerable": False})
        return results

    async def test_xss(test_client, endpoint: str, payloads: list):
        """Test XSS payloads"""
        results = []
        for payload in payloads:
            try:
                response = await test_client.get(f"{endpoint}?input={payload}")
                results.append(
                    {"payload": payload, "status_code": response.status_code, "reflected": payload in response.text}
                )
            except Exception as e:
                results.append({"payload": payload, "error": str(e), "reflected": False})
        return results

    return {"test_sql_injection": test_sql_injection, "test_xss": test_xss}


# Pytest configuration
def pytest_configure(config):
    """Configure pytest"""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "e2e: marks tests as end-to-end tests")
    config.addinivalue_line("markers", "load: marks tests as load tests")
    config.addinivalue_line("markers", "security: marks tests as security tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
