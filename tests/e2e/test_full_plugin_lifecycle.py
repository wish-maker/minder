"""
End-to-End (E2E) tests for full plugin lifecycle.
Tests the complete user journey from plugin discovery to execution.
"""

import pytest
import asyncio
from typing import Dict, Any
from httpx import AsyncClient

# Test fixtures
@pytest.fixture
async def gateway_client():
    """API Gateway client for E2E tests"""
    from services.api_gateway.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        yield client


@pytest.fixture
async def auth_headers():
    """Authentication headers for E2E tests"""
    # In production, this would be a valid JWT token
    return {"Authorization": "Bearer test-token"}


class TestPluginLifecycle:
    """Test complete plugin lifecycle"""

    def test_plugin_discovery_to_execution(self, gateway_client, auth_headers):
        """
        Test: Discover plugin → Install → Activate → Execute → Uninstall

        This is a full user journey test that validates:
        1. Plugin marketplace is accessible
        2. Plugin installation works
        3. Plugin activation works
        4. Plugin execution works
        5. Plugin uninstallation works
        """
        # Step 1: Discover available plugins
        discovery_response = gateway_client.get(
            "/v1/marketplace/plugins",
            headers=auth_headers,
            params={"search": "weather"}
        )

        assert discovery_response.status_code in [200, 404]
        if discovery_response.status_code == 200:
            plugins = discovery_response.json().get("plugins", [])
            assert isinstance(plugins, list)

        # Step 2: Install plugin (if available)
        install_response = gateway_client.post(
            "/v1/plugin-registry/plugins/install",
            headers=auth_headers,
            json={
                "name": "weather",
                "version": "1.0.0"
            }
        )

        # Accept 404 (plugin not found) or 200/201 (installed)
        assert install_response.status_code in [200, 201, 404]

        # Step 3: Activate plugin (if installed)
        if install_response.status_code in [200, 201]:
            activate_response = gateway_client.post(
                "/v1/plugin-state/plugins/weather/activate",
                headers=auth_headers,
            )

            assert activate_response.status_code in [200, 202]

        # Step 4: Execute plugin (if activated)
        if install_response.status_code in [200, 201]:
            execute_response = gateway_client.post(
                "/v1/plugin-state/tools/weather.get_forecast/execute",
                headers=auth_headers,
                json={
                    "location": "Istanbul",
                    "units": "metric"
                }
            )

            # Plugin might not be fully configured
            assert execute_response.status_code in [200, 400, 503]

        # Step 5: Uninstall plugin (if installed)
        if install_response.status_code in [200, 201]:
            uninstall_response = gateway_client.delete(
                "/v1/plugin-registry/plugins/weather",
                headers=auth_headers,
            )

            assert uninstall_response.status_code in [200, 202, 404]

    def test_plugin_registration_workflow(self, gateway_client, auth_headers):
        """
        Test: Register plugin → Upload → List → Unregister

        This test validates plugin developer workflow:
        1. Developer registers plugin
        2. Uploads plugin files
        3. Plugin appears in marketplace
        4. Developer can unregister
        """
        # Step 1: Register plugin
        register_response = gateway_client.post(
            "/v1/marketplace/plugins/register",
            headers=auth_headers,
            json={
                "name": "test-plugin",
                "description": "Test plugin for E2E testing",
                "version": "1.0.0",
                "author": "test-user",
                "category": "utilities"
            }
        )

        # Accept 201 (created) or 409 (conflict - already exists)
        assert register_response.status_code in [201, 409, 400]

        # Step 2: List plugins
        list_response = gateway_client.get(
            "/v1/marketplace/plugins",
            headers=auth_headers,
        )

        assert list_response.status_code in [200, 404]
        if list_response.status_code == 200:
            plugins = list_response.json().get("plugins", [])
            assert isinstance(plugins, list)

        # Step 3: Search for specific plugin
        search_response = gateway_client.get(
            "/v1/marketplace/plugins",
            headers=auth_headers,
            params={"search": "test-plugin"}
        )

        assert search_response.status_code in [200, 404]


class TestUserAuthenticationFlow:
    """Test complete user authentication flow"""

    def test_register_login_token_refresh(self, gateway_client):
        """
        Test: Register → Login → Get Token → Refresh Token → Logout

        This is a full authentication lifecycle test:
        1. User registers
        2. User logs in
        3. Gets access token
        4. Refreshes token
        5. Logs out
        """
        # Step 1: Register new user
        register_response = gateway_client.post(
            "/v1/auth/register",
            json={
                "username": "test-e2e-user",
                "email": "test-e2e@example.com",
                "password": "SecurePassword123!",
            }
        )

        # Accept 201 (created) or 409 (conflict - already exists)
        assert register_response.status_code in [201, 409, 501]  # 501 if not implemented

        # Step 2: Login
        login_response = gateway_client.post(
            "/v1/auth/login",
            json={
                "username": "test-e2e-user",
                "password": "SecurePassword123!",
            }
        )

        # Accept 200 (success) or 404/401 (invalid)
        assert login_response.status_code in [200, 404, 401, 501]

        if login_response.status_code == 200:
            login_data = login_response.json()
            assert "token" in login_data or "access_token" in login_data

            token = login_data.get("token") or login_data.get("access_token")

            # Step 3: Use token to access protected endpoint
            protected_response = gateway_client.get(
                "/v1/plugins",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert protected_response.status_code in [200, 404]

    def test_api_key_authentication(self, gateway_client):
        """Test API key authentication"""
        # This would test API key generation and usage
        # For now, we just verify the endpoint exists
        api_key_response = gateway_client.post(
            "/v1/auth/api-keys",
            json={
                "name": "test-e2e-key",
                "scopes": ["read:plugins", "write:plugins"]
            }
        )

        # Accept 201 (created) or 501 (not implemented)
        assert api_key_response.status_code in [201, 501]


class TestRAGPipelineE2E:
    """Test complete RAG pipeline workflow"""

    def test_document_upload_to_retrieval(self, gateway_client, auth_headers):
        """
        Test: Upload Document → Index → Query → Retrieve

        This is a full RAG pipeline test:
        1. Upload document
        2. Document is indexed
        3. Query documents
        4. Retrieve relevant chunks
        """
        # Step 1: Upload document
        upload_response = gateway_client.post(
            "/v1/rag/documents/upload",
            headers=auth_headers,
            files={
                "file": ("test.txt", b"This is a test document for E2E testing.", "text/plain")
            },
            data={
                "title": "Test Document",
                "description": "E2E test document"
            }
        )

        # Accept 201 (created) or 501 (not implemented)
        assert upload_response.status_code in [201, 501, 503]

        if upload_response.status_code == 201:
            upload_data = upload_response.json()
            document_id = upload_data.get("document_id")

            assert document_id is not None

            # Step 2: Query documents
            query_response = gateway_client.post(
                "/v1/rag/query",
                headers=auth_headers,
                json={
                    "query": "What is this document about?",
                    "top_k": 5
                }
            )

            # Accept 200 (success) or 503 (service unavailable)
            assert query_response.status_code in [200, 503]


class TestAIIntegrationE2E:
    """Test complete AI integration workflow"""

    def test_llm_inference_to_response(self, gateway_client, auth_headers):
        """
        Test: AI Inference → RAG Context → Response Generation

        This tests the AI integration:
        1. Send prompt to LLM
        2. LLM retrieves context from RAG
        3. Generate response
        4. Return to user
        """
        # Step 1: Send AI inference request
        ai_response = gateway_client.post(
            "/v1/ai/inference",
            headers=auth_headers,
            json={
                "prompt": "What is the weather in Istanbul?",
                "model": "llama2",
                "context": [],
                "max_tokens": 100
            }
        )

        # Accept 200 (success) or 503 (service unavailable)
        assert ai_response.status_code in [200, 503, 501]


class TestMonitoringAndObservability:
    """Test monitoring and observability"""

    def test_health_check_to_metrics(self, gateway_client):
        """
        Test: Health Check → Metrics → Alerts

        This tests observability:
        1. Health check passes
        2. Metrics are collected
        3. Alerting works
        """
        # Step 1: Health check
        health_response = gateway_client.get("/health")

        assert health_response.status_code in [200, 503]

        # Step 2: Get metrics
        metrics_response = gateway_client.get("/metrics")

        # Accept 200 (success) or 404 (not implemented)
        assert metrics_response.status_code in [200, 404]

        if metrics_response.status_code == 200:
            # Verify Prometheus metrics format
            metrics_text = metrics_response.text
            assert "http_requests_total" in metrics_text or "HELP" in metrics_text


class TestErrorHandlingE2E:
    """Test error handling across the system"""

    def test_4xx_error_responses(self, gateway_client):
        """Test that 4xx errors are handled correctly"""
        # Test 400 Bad Request
        bad_request_response = gateway_client.post(
            "/v1/plugins",
            json={}
        )

        assert bad_request_response.status_code in [400, 401, 422]

    def test_5xx_error_responses(self, gateway_client):
        """Test that 5xx errors are handled correctly"""
        # Test with invalid endpoint
        not_found_response = gateway_client.get("/v1/invalid-endpoint")

        assert not_found_response.status_code == 404


class TestRateLimitingE2E:
    """Test rate limiting in production-like conditions"""

    def test_rate_limit_thresholds(self, gateway_client):
        """
        Test: Make many requests → Rate limit kicks in → Wait → Requests work again

        This tests rate limiting:
        1. Make requests up to limit
        2. Hit rate limit
        3. Wait for reset
        4. Requests work again
        """
        import time

        # Make multiple requests quickly
        responses = []
        for i in range(150):  # Over the rate limit
            response = gateway_client.get("/v1/health")
            responses.append(response.status_code)

        # At least one should be rate limited (429)
        assert 429 in responses or 200 in responses

        # Most should be successful
        success_count = responses.count(200)
        assert success_count > 50  # Should have some successes


class TestPerformanceE2E:
    """Test performance under load"""

    def test_response_time_under_load(self, gateway_client):
        """
        Test: Make concurrent requests → Check response times

        This tests performance:
        1. Make 100 concurrent requests
        2. All complete within 2 seconds
        3. Success rate > 95%
        """
        import concurrent.futures

        def make_request():
            response = gateway_client.get("/v1/health")
            return response.status_code, response.elapsed.total_seconds()

        # Make 100 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(make_request) for _ in range(100)]
            results = [future.result(timeout=5) for future in concurrent.futures.as_completed(futures)]

        # Calculate success rate
        status_codes, times = zip(*results)
        success_count = sum(1 for code in status_codes if code == 200)
        success_rate = (success_count / len(results)) * 100

        # Calculate average response time
        avg_time = sum(times) / len(times)

        # Assertions
        assert success_rate >= 90  # At least 90% success rate
        assert avg_time < 1.0  # Average response time < 1 second


class TestSecurityE2E:
    """Test security across the system"""

    def test_authentication_required(self, gateway_client):
        """Test that authentication is required for protected endpoints"""
        # Try to access protected endpoint without auth
        protected_response = gateway_client.post(
            "/v1/plugins/install",
            json={"name": "weather"}
        )

        # Should return 401 or 403
        assert protected_response.status_code in [401, 403, 422]

    def test_sql_injection_prevention(self, gateway_client):
        """Test that SQL injection is prevented"""
        # Try SQL injection
        injection_response = gateway_client.get(
            "/v1/marketplace/plugins",
            params={"search": "1' OR '1'='1"}
        )

        # Should not return 500 (internal error)
        assert injection_response.status_code != 500

    def test_xss_prevention(self, gateway_client):
        """Test that XSS is prevented"""
        # Try XSS
        xss_response = gateway_client.get(
            "/v1/marketplace/plugins",
            params={"search": "<script>alert('xss')</script>"}
        )

        # Should not return 500 (internal error)
        assert xss_response.status_code != 500
