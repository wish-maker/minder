"""
Test Plugin Registry Proxy Functionality
Tests for dynamic proxy routing to plugin microservices
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

# Skip this test if plugin registry dependencies are not available
try:
    # Add plugin registry to path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "plugin-registry"))
    from routes.plugins import ProxyRouter

    PROXY_ROUTER_AVAILABLE = True
except ImportError:
    PROXY_ROUTER_AVAILABLE = False
    pytest.skip("Plugin Registry dependencies not available", allow_module_level=True)


# Define ServiceRegistration locally to avoid config issues
class ServiceRegistration(BaseModel):
    """Service registration for service discovery"""

    service_name: str
    service_type: str
    host: str
    port: int
    health_check_url: str = "/health"
    metadata: dict = {}


@pytest.fixture
def sample_service():
    """Create sample service registration"""
    return ServiceRegistration(
        service_name="crypto-plugin",
        service_type="plugin",
        host="localhost",
        port=8002,
        health_check_url="/health",
        metadata={"version": "1.0.0"},
    )


@pytest.fixture
def services_db(sample_service):
    """Create services database with sample service"""
    return {"crypto-plugin": sample_service}


@pytest.fixture
def proxy_router(services_db):
    """Create proxy router instance"""
    return ProxyRouter(services_db)


@pytest.mark.asyncio
async def test_proxy_router_initialization(proxy_router):
    """Test proxy router initializes correctly"""
    assert proxy_router.services_db is not None
    assert len(proxy_router.services_db) == 1
    assert proxy_router.http_client is None


@pytest.mark.asyncio
async def test_get_http_client(proxy_router):
    """Test HTTP client creation"""
    client = await proxy_router.get_http_client()
    assert client is not None
    assert proxy_router.http_client is not None


@pytest.mark.asyncio
async def test_health_check_proxy_success(proxy_router, sample_service):
    """Test successful health check proxy"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "healthy", "service": "crypto-plugin"}

    with patch.object(proxy_router, "get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        async_mock_get = AsyncMock()
        async_mock_get.return_value = mock_response
        mock_client.get = async_mock_get

        result = await proxy_router.health_check_proxy("crypto-plugin")

        assert result["status"] == "healthy"
        assert result["service"] == "crypto-plugin"
        async_mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_proxy_service_not_found(proxy_router):
    """Test health check with non-existent service"""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await proxy_router.health_check_proxy("non-existent")

    assert exc_info.value.status_code == 404
    assert "not registered" in exc_info.value.detail


@pytest.mark.asyncio
async def test_forward_request_success(proxy_router, sample_service):
    """Test successful request forwarding"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"symbol": "BTC", "price": 50000}'
    mock_response.headers = {"content-type": "application/json"}

    mock_request = MagicMock()
    mock_request.method = "GET"
    mock_request.body = AsyncMock(return_value=b"")
    mock_request.headers = {"host": "localhost"}
    mock_request.query_params = {}
    mock_request.url = MagicMock()
    mock_request.url.path = "/analysis"
    mock_request.url.query = ""

    with patch.object(proxy_router, "get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        async_mock_request = AsyncMock()
        async_mock_request.return_value = mock_response
        mock_client.request = async_mock_request

        from fastapi import Response

        result = await proxy_router.forward_request("crypto-plugin", "/analysis", mock_request)

        assert isinstance(result, Response)
        assert result.status_code == 200
        async_mock_request.assert_called_once()


@pytest.mark.asyncio
async def test_forward_request_service_not_found(proxy_router):
    """Test forward request with non-existent service"""
    from fastapi import HTTPException, Request

    mock_request = MagicMock(spec=Request)

    with pytest.raises(HTTPException) as exc_info:
        await proxy_router.forward_request("non-existent", "/test", mock_request)

    assert exc_info.value.status_code == 404
    assert "not registered" in exc_info.value.detail


@pytest.mark.asyncio
async def test_close_http_client(proxy_router):
    """Test HTTP client cleanup"""
    # Create client first
    await proxy_router.get_http_client()
    assert proxy_router.http_client is not None

    # Close client
    await proxy_router.close()
    assert proxy_router.http_client is None
