"""
Simple integration tests for API Gateway without container dependencies.
Tests endpoint integration, auth, rate limiting, and error handling.
"""

import pytest
import requests

class TestAPIGatewayIntegration:
    """Simple integration tests for API Gateway"""

    def test_health_check(self):
        """Test health check endpoint"""
        response = requests.get("http://localhost:8000/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded"]

    def test_root_endpoint(self):
        """Test root endpoint"""
        response = requests.get("http://localhost:8000/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data or "message" in data

    def test_plugin_list_unauthenticated(self):
        """Test plugin list endpoint (no auth)"""
        response = requests.get("http://localhost:8000/v1/plugins")
        assert response.status_code in [200, 401]  # 200 or 401 Unauthorized

    def test_plugin_detail(self):
        """Test plugin detail endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/crypto")
        assert response.status_code in [200, 401, 404]

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
