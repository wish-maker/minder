"""Real E2E coverage for plugin discovery + read-only action invocation (#318
phase 2/5), replacing test_full_plugin_lifecycle.py / test_service_integration.py.

Exercises the REAL crypto/weather/news/tefas plugins loaded from disk by a
REAL plugin-registry process, both directly and proxied through a REAL
api-gateway process — confirming #254's GET-unauthenticated /
POST-JWT-gated split actually holds end-to-end, not just at the unit-test
level (tests/unit/test_registry_plugin_read_actions.py already covers the
route logic in isolation; this proves the real deployed topology agrees).

These plugins call real third-party APIs (Yahoo Finance, a public geocoding/
weather API, RSS feeds, a Turkish fund API) — assertions check response
*structure*, not exact values, so real-world data changes (prices, headline
counts) don't make the suite flaky.
"""

import httpx


def test_plugins_loaded_from_disk(live_stack):
    resp = httpx.get(f"{live_stack.registry_url}/v1/plugins", timeout=10.0)
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()["plugins"]}
    # The 4 data plugins #254 split GET/POST for -- confirms real plugin
    # loading (schema.sql, plugin_loader.py) actually worked, not just health.
    assert {"crypto", "weather", "news", "tefas"} <= names


def test_read_only_action_direct_on_registry_unauthenticated(live_stack):
    resp = httpx.get(
        f"{live_stack.registry_url}/v1/plugins/crypto/actions/get_price",
        params={"coin": "bitcoin"},
        timeout=15.0,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["plugin"] == "crypto"
    assert body["action"] == "get_price"
    assert "close" in body["result"] or "error" in body["result"]


def test_read_only_action_via_gateway_proxy_unauthenticated(live_stack):
    """Same action, but through api-gateway's generic /v1/plugins/* proxy --
    confirms _require_jwt_for_writes correctly leaves GET untouched end-to-end."""
    resp = httpx.get(
        f"{live_stack.gateway_url}/v1/plugins/weather/actions/get_weather",
        params={"location": "Istanbul"},
        timeout=15.0,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["plugin"] == "weather"
    assert body["action"] == "get_weather"


def test_news_read_only_action_with_optional_params(live_stack):
    # No `feed` filter -> fetches every configured RSS feed sequentially from
    # real external servers; CI's network latency to those feeds is more
    # variable than this sandbox's, so this needs more headroom than the
    # other single-request plugin actions here (#318 phase 2 follow-up).
    resp = httpx.get(
        f"{live_stack.registry_url}/v1/plugins/news/actions/get_news",
        params={"limit": 3},
        timeout=30.0,
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert "headlines" in result or "error" in result


def test_mutating_action_rejects_unauthenticated_post(live_stack):
    resp = httpx.post(
        f"{live_stack.gateway_url}/v1/plugins/crypto/actions/refresh",
        json={},
        timeout=10.0,
    )
    assert resp.status_code == 401


def test_mutating_action_not_reachable_via_get(live_stack):
    """ "refresh" is in ACTIONS but deliberately NOT in READ_ONLY_ACTIONS -- GET
    must 404, never silently run a mutation unauthenticated (#254's security
    boundary)."""
    resp = httpx.get(
        f"{live_stack.registry_url}/v1/plugins/crypto/actions/refresh", timeout=10.0
    )
    assert resp.status_code == 404


def test_unknown_action_404(live_stack):
    resp = httpx.get(
        f"{live_stack.registry_url}/v1/plugins/crypto/actions/delete_everything",
        timeout=10.0,
    )
    assert resp.status_code == 404


def test_missing_required_param_400(live_stack):
    resp = httpx.get(
        f"{live_stack.registry_url}/v1/plugins/crypto/actions/get_price", timeout=10.0
    )
    assert resp.status_code == 400
