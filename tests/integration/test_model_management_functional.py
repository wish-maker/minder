"""
Functional tests for the model-management service (Ollama-backed).

Covers the endpoints that moved into routes/models_api.py during the 2026-07-10
refactor: health, list, test (real inference), and the constraints/metrics
placeholders. Skips automatically if the service is unreachable.
"""

import os

import httpx
import pytest

BASE = os.environ.get("MINDER_MODEL_MGMT_URL", "http://localhost:8005")


def _up() -> bool:
    try:
        return httpx.get(f"{BASE}/health", timeout=3.0).status_code == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _up(), reason="model-management not reachable on :8005"),
]


def test_health():
    r = httpx.get(f"{BASE}/health", timeout=8.0)
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_list_models_returns_local_models():
    r = httpx.get(f"{BASE}/models", timeout=15.0)
    assert r.status_code == 200
    models = r.json()
    assert isinstance(models, list)
    # a clean install pulls at least one model (nomic-embed-text / llama3.2)
    for m in models:
        assert {"id", "name", "provider", "status"} <= set(m)


def test_constraints_is_placeholder():
    r = httpx.post(
        f"{BASE}/models/anything/constraints",
        json={
            "rate_limit": 1,
            "cost_limit": 1.0,
            "allowed_users": [],
            "content_filtering": False,
            "max_tokens": 1,
        },
        timeout=8.0,
    )
    assert r.status_code == 200
    assert "placeholder" in r.json().get("message", "").lower()


def test_metrics_placeholder_returns_zeros():
    r = httpx.get(f"{BASE}/models/anything/metrics", timeout=8.0)
    assert r.status_code == 200
    body = r.json()
    assert body["total_requests"] == 0
    assert "not yet implemented" in body["note"].lower()


def test_root():
    r = httpx.get(f"{BASE}/", timeout=8.0)
    assert r.status_code == 200
    assert r.json()["name"] == "Minder Model Management"
