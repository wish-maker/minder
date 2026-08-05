import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.integration]


def test_marketplace_api_starts(marketplace_app_isolated):
    """Test that marketplace API starts successfully"""
    client = TestClient(marketplace_app_isolated.app)

    # Health check
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data
    assert data["service"] == "marketplace"


def test_marketplace_api_docs_available(marketplace_app_isolated):
    """Test that API documentation is available"""
    client = TestClient(marketplace_app_isolated.app)

    # OpenAPI docs
    response = client.get("/docs")
    assert response.status_code == 200

    # OpenAPI schema
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "info" in schema
