# services/marketplace/tests/test_main.py
from fastapi.testclient import TestClient


def test_marketplace_api_starts():
    """Test that marketplace API starts successfully"""
    from services.marketplace.main import app

    client = TestClient(app)

    # Health check
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data
    assert data["service"] == "marketplace"


def test_marketplace_api_docs_available():
    """Test that API documentation is available"""
    from services.marketplace.main import app

    client = TestClient(app)

    # OpenAPI docs
    response = client.get("/docs")
    assert response.status_code == 200

    # OpenAPI schema
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "info" in schema
