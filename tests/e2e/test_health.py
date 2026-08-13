"""Harness smoke test (#318): every real service is reachable over a real
socket and reports its actual dependency checks as healthy."""

import httpx


def test_gateway_health(live_stack):
    resp = httpx.get(f"{live_stack.gateway_url}/health", timeout=5.0)
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "api-gateway"
    assert body["status"] == "healthy"
    assert body["checks"]["redis"] == "healthy"
    assert body["checks"]["plugin_registry"] == "healthy"
    assert body["checks"]["rag_pipeline"] == "healthy"
    # model-management joined this harness in #437 -- real process, real check.
    assert body["checks"]["model_management"] == "healthy"


def test_model_management_health(live_stack):
    resp = httpx.get(f"{live_stack.model_mgmt_url}/health", timeout=5.0)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"


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
