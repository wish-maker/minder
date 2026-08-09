"""
Integration tests for API Gateway.
Tests endpoint integration, proxying, and error handling using
gateway_test_client (tests/conftest.py) -- an in-process TestClient wrapping
the real app, with no live downstream services (plugin-registry/rag-pipeline/
model-management aren't actually running), so any proxied request
deterministically gets a real httpx.ConnectError -> 503 from routes/proxy.py.

Checked against the real running app (#333) -- the original version of this
file asserted three fictional route prefixes (/registry/v1/plugins,
/marketplace/v1/plugins, /rag/v1/query -- none of these exist; the real
prefix is /v1/rag/*, not /rag/v1/*), used two fixtures that were never
defined anywhere in this repo (security_tester, load_tester), and several
tests asserted a security boundary that contradicts the gateway's actual,
intentional design (#254: GET is never auth-gated, only mutating methods
are) -- that real boundary is already covered end-to-end in
tests/e2e/test_plugin_actions.py against a real running plugin-registry.
"""

import pytest

pytestmark = [pytest.mark.integration]


class TestAPIGatewayIntegration:
    """Integration tests for API Gateway"""

    def test_health_check(self, gateway_test_client):
        """Test health check endpoint"""
        response = gateway_test_client.get("/health")
        # 503/degraded is real and expected here: plugin-registry/rag-pipeline
        # aren't actually running for this in-process client.
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_plugin_list_unauthenticated(self, gateway_test_client):
        """GET /v1/plugins is never auth-gated (#254) -- only real outcomes
        here are a real proxied response or a real downstream-unreachable 503."""
        response = gateway_test_client.get("/v1/plugins")
        assert response.status_code in [200, 503]

    def test_plugin_detail(self, gateway_test_client):
        """GET /v1/plugins/{name} proxies through the same generic wildcard."""
        response = gateway_test_client.get("/v1/plugins/crypto")
        assert response.status_code in [200, 503]

    def test_proxy_to_model_management(self, gateway_test_client):
        """/v1/models proxies to model-management (#147/C1: no /v1/models/models
        doubling)."""
        response = gateway_test_client.get("/v1/models")
        assert response.status_code in [200, 503]

    def test_bundle_list_unauthenticated(self, gateway_test_client):
        """GET /v1/bundles is a read, so it's never auth-gated -- only real
        outcomes here are a real proxied response or downstream-unreachable 503."""
        response = gateway_test_client.get("/v1/bundles")
        assert response.status_code in [200, 503]

    def test_bundle_enable_requires_auth(self, gateway_test_client):
        """POST /v1/bundles/{name}/enable is a write, so it's auth-gated (mirrors
        /v1/plugins/{path:path}'s _require_jwt_for_writes)."""
        response = gateway_test_client.post("/v1/bundles/news/enable")
        assert response.status_code == 401

    def test_cors_headers(self, gateway_test_client):
        """CORSMiddleware (shared/utils/cors.py) only treats a request as a
        real preflight when it carries Origin + Access-Control-Request-Method
        -- without those, OPTIONS just 405s like any other unregistered
        method, which is not a CORS bug."""
        response = gateway_test_client.options(
            "/v1/plugins",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_invalid_path(self, gateway_test_client):
        """Test invalid path"""
        response = gateway_test_client.get("/invalid/path")
        assert response.status_code == 404

    def test_method_not_allowed(self, gateway_test_client):
        """POST /v1/plugins has no handler (only GET is registered on this
        exact path; mutations go through /v1/plugins/{plugin}/actions/{action})."""
        response = gateway_test_client.post("/v1/plugins")
        assert response.status_code == 405

    def test_rate_limiting_does_not_block_a_single_request(self, gateway_test_client):
        """Rate limiting is real (Redis-backed, core/middleware.py) and its
        counter is keyed per client IP on the shared, session-scoped gateway
        app -- deliberately hammering requests here (as the original version
        of this test did, up to 20 in a loop) trips the real limiter and then
        poisons every OTHER test in the session sharing gateway_test_client
        with 429s, since RATE_LIMIT_ENABLED=false (tests/conftest.py) is set
        before the shared app's collection-time import specifically so this
        can't happen. This only confirms ordinary single-request traffic
        isn't blocked; the real blocking path is covered by
        test_rate_limiting_actually_blocks_the_nth_request below, against a
        SEPARATE isolated app with rate limiting genuinely enabled."""
        response = gateway_test_client.get("/v1/plugins")
        assert response.status_code in [200, 503]

    def test_rate_limiting_actually_blocks_the_nth_request(
        self, api_gateway_rate_limited_app
    ):
        """#357: the real Redis-backed blocking path (a request past
        RATE_LIMIT_PER_MINUTE actually getting a 429) had zero test coverage
        anywhere -- the only existing rate-limit test (above) can't exercise
        it, since it deliberately runs against an app with rate limiting
        disabled. api_gateway_rate_limited_app (tests/conftest.py) is a
        separate, freshly-imported app with RATE_LIMIT_ENABLED=true and
        RATE_LIMIT_PER_MINUTE=3, isolated from the shared session app so this
        can safely hammer requests without poisoning any other test."""
        from fastapi.testclient import TestClient

        from shared.utils.redis_client import create_redis_client_from_settings

        app_module = api_gateway_rate_limited_app
        client = TestClient(app_module.app)

        # get_remote_address() keys the limiter by the caller's IP; clear any
        # stale counter from a previous run so this test is deterministic.
        redis_client = create_redis_client_from_settings(
            app_module.settings, ping=False
        )
        # Starlette's TestClient sets request.client.host to the literal string
        # "testclient" (not a real IP) -- verified directly; get_remote_address()
        # only falls back to "127.0.0.1" when request.client is None entirely.
        test_ip = "testclient"
        redis_client.delete(f"ratelimit:{test_ip}")

        try:
            responses = [client.get("/v1/plugins") for _ in range(4)]
        finally:
            redis_client.delete(f"ratelimit:{test_ip}")

        # First 3 (the configured RATE_LIMIT_PER_MINUTE) are real requests --
        # 200/503 depending on the (unrunning) downstream, never 429 yet.
        assert all(r.status_code != 429 for r in responses[:3])
        # The 4th must be rejected -- this is the actual mechanism this test
        # exists to prove works at all.
        assert responses[3].status_code == 429
        body = responses[3].json()
        assert body["limit"] == 3


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


class TestAPIGatewayValidation:
    """These exercise the generic proxy wildcard, not gateway-level
    validation -- the gateway itself does no input validation on these
    paths, it only forwards to plugin-registry (unreachable here, so always
    503 in this in-process harness). Real per-field validation (e.g. a
    missing required action param) is covered against a real running
    plugin-registry in tests/e2e/test_plugin_actions.py."""

    def test_invalid_plugin_name(self, gateway_test_client):
        response = gateway_test_client.get("/v1/plugins/invalid name!")
        assert response.status_code in [404, 503]

    def test_invalid_query_params(self, gateway_test_client):
        response = gateway_test_client.get("/v1/plugins?page=invalid")
        assert response.status_code in [200, 503]

    def test_negative_page_number(self, gateway_test_client):
        response = gateway_test_client.get("/v1/plugins?page=-1")
        assert response.status_code in [200, 503]


@pytest.mark.integration
class TestAPIGatewayDatabaseIntegration:
    """Test database integration in API Gateway"""

    def test_database_connection(self, gateway_test_client):
        """Test database connection through gateway"""
        response = gateway_test_client.get("/health")
        assert response.status_code in [200, 503]

        data = response.json()
        assert "checks" in data
