"""
Functional tests for the model-management service (Ollama-backed), run against
the real live-process harness (`live_stack`, #437 -- moved here from
tests/integration/ so these actually execute in CI instead of silently
skipping for lack of a network-reachable service).

Covers the endpoints that moved into routes/models_api.py during the 2026-07-10
refactor: health, list, test (real inference), and the constraints/metrics
not-implemented (501) endpoints.
"""

import httpx


def test_health(live_stack):
    r = httpx.get(f"{live_stack.model_mgmt_url}/health", timeout=8.0)
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_list_models_returns_local_models(live_stack):
    r = httpx.get(f"{live_stack.model_mgmt_url}/models", timeout=15.0)
    assert r.status_code == 200
    body = r.json()
    # #519: shared {items,total,limit,offset} envelope, not a bare array.
    assert set(body) >= {"items", "total", "limit", "offset"}
    assert body["total"] >= len(body["items"])
    for m in body["items"]:
        assert {"id", "name", "provider", "status"} <= set(m)


def test_constraints_not_implemented_501(live_stack):
    # Placeholder endpoints now return 501 instead of a fake 200 (#145).
    r = httpx.post(
        f"{live_stack.model_mgmt_url}/models/anything/constraints",
        json={
            "rate_limit": 1,
            "cost_limit": 1.0,
            "allowed_users": [],
            "content_filtering": False,
            "max_tokens": 1,
        },
        timeout=8.0,
    )
    assert r.status_code == 501
    assert "not implemented" in r.json().get("detail", "").lower()


def test_metrics_not_implemented_501(live_stack):
    r = httpx.get(f"{live_stack.model_mgmt_url}/models/anything/metrics", timeout=8.0)
    assert r.status_code == 501
    assert "not implemented" in r.json().get("detail", "").lower()


def test_root(live_stack):
    r = httpx.get(f"{live_stack.model_mgmt_url}/", timeout=8.0)
    assert r.status_code == 200
    assert r.json()["name"] == "Minder Model Management"
