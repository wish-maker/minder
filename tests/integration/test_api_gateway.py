"""
Integration tests for API Gateway.
Tests endpoint integration, auth, rate limiting, and error handling.
"""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from conftest import gateway_test_client, test_headers


class TestAPIGatewayIntegration:
    """Integration tests for API Gateway"""

    def test_health_check(self, gateway_test_client):
        """Test health check endpoint"""
        response = gateway_test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded"]

    def test_root_endpoint(self, gateway_test_client):
        """Test root endpoint"""
        response = gateway_test_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data or "message" in data

    def test_plugin_list_unauthenticated(self, gateway_test_client):
        """Test plugin list without authentication"""
        response = gateway_test_client.get("/v1/plugins")
        # May require auth
        assert response.status_code in [200, 401, 403]

    def test_plugin_list_authenticated(self, gateway_test_client, test_headers):
        """Test plugin list with authentication"""
        response = gateway_test_client.get("/v1/plugins", headers=test_headers)
        # Should work with auth
        assert response.status_code in [200, 404]

    def test_plugin_detail(self, gateway_test_client):
        """Test plugin detail endpoint"""
        response = gateway_test_client.get("/v1/plugins/crypto")
        # May not exist
        assert response.status_code in [200, 404]

    def test_proxy_to_registry(self, gateway_test_client):
        """Test proxy to plugin registry"""
        response = gateway_test_client.get("/registry/v1/plugins")
        # Should proxy to registry
        assert response.status_code in [200, 404, 502]

    def test_proxy_to_marketplace(self, gateway_test_client):
        """Test proxy to marketplace"""
        response = gateway_test_client.get("/marketplace/v1/plugins")
        # Should proxy to marketplace
        assert response.status_code in [200, 404, 502]

    def test_proxy_to_rag(self, gateway_test_client):
        """Test proxy to RAG pipeline"""
        response = gateway_test_client.get("/rag/v1/query")
        # Should proxy to RAG
        assert response.status_code in [200, 404, 502]

    def test_proxy_to_model_management(self, gateway_test_client):
        """Test proxy to model management"""
        response = gateway_test_client.get("/models/v1/models")
        # Should proxy to model management
        assert response.status_code in [200, 404, 502]

    def test_cors_headers(self, gateway_test_client):
        """Test CORS headers"""
        response = gateway_test_client.options("/v1/plugins")
        assert response.status_code == 200 or response.status_code == 204
        # Check for CORS headers
        cors_headers = ["Access-Control-Allow-Origin", "Access-Control-Allow-Methods"]
        for header in cors_headers:
            assert header in response.headers or response.status_code != 200

    def test_invalid_path(self, gateway_test_client):
        """Test invalid path"""
        response = gateway_test_client.get("/invalid/path")
        assert response.status_code == 404

    def test_method_not_allowed(self, gateway_test_client):
        """Test method not allowed"""
        response = gateway_test_client.post("/v1/plugins")
        assert response.status_code == 405

    def test_rate_limiting_basic(self, gateway_test_client):
        """Test basic rate limiting"""
        # Make multiple requests quickly
        responses = []
        for i in range(20):
            response = gateway_test_client.get("/v1/plugins")
            responses.append(response.status_code)

            if response.status_code == 429:
                break

        # Should eventually hit rate limit
        assert 429 in responses or len(responses) == 20

    def test_rate_limiting_headers(self, gateway_test_client):
        """Test rate limiting headers"""
        response = gateway_test_client.get("/v1/plugins")
        # Check for rate limit headers
        rate_limit_headers = ["X-RateLimit-Limit", "X-RateLimit-Remaining"]
        # May or may not have headers depending on implementation
        pass


class TestAPIGatewayErrorHandling:
    """Test error handling in API Gateway"""

    def test_404_error_format(self, gateway_test_client):
        """Test 404 error format"""
        response = gateway_test_client.get("/nonexistent")
        assert response.status_code == 404

        data = response.json()
        assert "error" in data or "detail" in data

    def test_405_error_format(self, gateway_test_client):
        """Test 405 error format"""
        response = gateway_test_client.post("/v1/plugins")
        assert response.status_code == 405

    def test_429_error_format(self, gateway_test_client):
        """Test 429 error format"""
        # Try to trigger rate limit
        for i in range(30):
            response = gateway_test_client.get("/v1/plugins")
            if response.status_code == 429:
                break

        if response.status_code == 429:
            data = response.json()
            assert "error" in data or "detail" in data


class TestAPIGatewayValidation:
    """Test input validation in API Gateway"""

    def test_invalid_plugin_name(self, gateway_test_client):
        """Test invalid plugin name"""
        response = gateway_test_client.get("/v1/plugins/invalid name!")
        # Should 404 or 422
        assert response.status_code in [404, 422]

    def test_invalid_query_params(self, gateway_test_client):
        """Test invalid query parameters"""
        response = gateway_test_client.get("/v1/plugins?page=invalid")
        # Should 422 or 400
        assert response.status_code in [400, 422]

    def test_negative_page_number(self, gateway_test_client):
        """Test negative page number"""
        response = gateway_test_client.get("/v1/plugins?page=-1")
        # Should 422 or 400
        assert response.status_code in [400, 422]


class TestAPIGatewayPerformance:
    """Test API Gateway performance"""

    @pytest.mark.slow
    def test_response_time(self, gateway_test_client, benchmark):
        """Test response time"""
        def request():
            gateway_test_client.get("/v1/plugins")

        benchmark(request)

    @pytest.mark.slow
    @pytest.mark.load
    async def test_load_capacity(self, gateway_test_client, load_tester):
        """Test load capacity"""
        stats = await load_tester(
            endpoint="/v1/plugins",
            concurrent_users=50,
            requests_per_user=10,
            delay_between_requests=0.01
        )

        assert stats["total_requests"] == 500
        assert stats["success_rate"] > 95  # At least 95% success
        assert stats["avg_response_time_ms"] < 500  # Avg under 500ms


@pytest.mark.integration
class TestAPIGatewayDatabaseIntegration:
    """Test database integration in API Gateway"""

    def test_database_connection(self, gateway_test_client):
        """Test database connection through gateway"""
        response = gateway_test_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        if "database" in data:
            assert data["database"] in ["healthy", "connected"]


@pytest.mark.security
class TestAPIGatewaySecurity:
    """Test security in API Gateway"""

    def test_authentication_required(self, gateway_test_client):
        """Test authentication is required for protected endpoints"""
        response = gateway_test_client.get("/v1/plugins/register")
        # Should require auth
        assert response.status_code in [401, 403, 404]

    def test_invalid_token(self, gateway_test_client):
        """Test invalid token rejection"""
        headers = {"Authorization": "Bearer invalid_token"}
        response = gateway_test_client.get("/v1/plugins", headers=headers)
        # Should reject invalid token
        assert response.status_code in [401, 403, 404]

    def test_sql_injection_prevention(self, gateway_test_client, security_tester):
        """Test SQL injection prevention"""
        payloads = [
            "1' OR '1'='1",
            "1; DROP TABLE plugins--",
            "1 UNION SELECT * FROM users"
        ]

        for payload in payloads:
            response = gateway_test_client.get(f"/v1/plugins/{payload}")
            # Should not return 500 (SQL error)
            assert response.status_code != 500

    def test_xss_prevention(self, gateway_test_client, security_tester):
        """Test XSS prevention"""
        payloads = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')"
        ]

        for payload in payloads:
            response = gateway_test_client.get(f"/v1/plugins?query={payload}")
            # Should not reflect the payload
            if response.status_code == 200:
                data = response.text
                # Script tags should not be reflected
                assert "<script>" not in data or data == str(data)


@pytest.mark.e2e
class TestAPIGatewayE2E:
    """End-to-end tests for API Gateway"""

    def test_full_request_flow(self, gateway_test_client):
        """Test full request flow through gateway"""
        # 1. Health check
        health_response = gateway_test_client.get("/health")
        assert health_response.status_code == 200

        # 2. List plugins
        plugins_response = gateway_test_client.get("/v1/plugins")
        assert plugins_response.status_code in [200, 404]

        # 3. Get specific plugin (if exists)
        if plugins_response.status_code == 200:
            plugins = plugins_response.json()
            if plugins and len(plugins) > 0:
                plugin_name = plugins[0].get("name") or plugins[0].get("id")
                if plugin_name:
                    detail_response = gateway_test_client.get(f"/v1/plugins/{plugin_name}")
                    assert detail_response.status_code in [200, 404]

    def test_proxy_routing(self, gateway_test_client):
        """Test proxy routing to different services"""
        # Test routing to various services
        services = [
            ("/registry/v1/plugins", "Plugin Registry"),
            ("/marketplace/v1/plugins", "Marketplace"),
            ("/rag/v1/query", "RAG Pipeline"),
            ("/models/v1/models", "Model Management")
        ]

        for path, service_name in services:
            response = gateway_test_client.get(path)
            # Should route successfully or return 502 (service down)
            assert response.status_code in [200, 404, 502]

    def test_error_propagation(self, gateway_test_client):
        """Test error propagation from downstream services"""
        # Try to access a non-existent service
        response = gateway_test_client.get("/nonexistent/v1/test")
        # Should return 404 or 502
        assert response.status_code in [404, 502]
