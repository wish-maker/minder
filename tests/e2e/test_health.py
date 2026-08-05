"""Harness smoke test (#318): every real service is reachable over a real
socket and reports its actual dependency checks as healthy."""

import httpx


def test_gateway_health(live_stack):
    resp = httpx.get(f"{live_stack.gateway_url}/health", timeout=5.0)
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "api-gateway"
    # "degraded" (still 200) is correct/expected here: model-management isn't
    # part of this harness's minimal 3-service set, and it's a non-critical
    # dependency at the default MINDER_PHASE=1 (routes/health.py's _PHASE_2).
    assert body["status"] in ("healthy", "degraded")
    assert body["checks"]["redis"] == "healthy"
    assert body["checks"]["plugin_registry"] == "healthy"
    assert body["checks"]["rag_pipeline"] == "healthy"


def test_plugin_registry_health(live_stack):
    resp = httpx.get(f"{live_stack.registry_url}/health", timeout=5.0)
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "plugin-registry"
    assert body["status"] == "healthy"
    assert body["checks"]["postgres"] == "healthy"
    assert body["checks"]["redis"] == "healthy"


def test_rag_pipeline_health(live_stack):
    resp = httpx.get(f"{live_stack.rag_url}/health", timeout=5.0)
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "rag-pipeline"
    assert body["status"] == "healthy"
    assert body["checks"]["qdrant"] == "healthy"


def test_gateway_can_reach_plugin_registry_over_real_network(live_stack):
    """Not a health check on plugin-registry itself -- confirms api-gateway's
    OWN outbound httpx call to it, over a real socket, actually works."""
    resp = httpx.get(f"{live_stack.gateway_url}/v1/plugins", timeout=5.0)
    assert resp.status_code == 200
    assert "plugins" in resp.json()
