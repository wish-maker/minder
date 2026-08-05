"""Real E2E coverage for downstream error propagation through api-gateway's
generic proxy (#318 phase 5/5).

routes/proxy.py's `proxy_request` re-serializes whatever the downstream
service actually returned (status_code + response.json()) rather than a
fabricated status-code allowlist -- the old fictional suite accepted
`status_code in [200, 201, 404, 501, 503]` for nearly anything, so it could
never catch the gateway silently swallowing or rewriting a real error. These
tests assert an EXACT status code and, where practical, that the body is
byte-for-byte identical to calling the backing service directly -- proving
the proxy really is transparent.

The unauthenticated-mutating-action security boundary (401) is already
covered end-to-end in test_plugin_actions.py
(test_mutating_action_rejects_unauthenticated_post) -- not duplicated here.
"""

import httpx


def test_plugin_registry_404_propagates_through_gateway_proxy_exactly(live_stack):
    direct = httpx.get(
        f"{live_stack.registry_url}/v1/plugins/crypto/actions/delete_everything",
        timeout=10.0,
    )
    proxied = httpx.get(
        f"{live_stack.gateway_url}/v1/plugins/crypto/actions/delete_everything",
        timeout=10.0,
    )
    assert direct.status_code == 404
    assert proxied.status_code == 404
    assert proxied.json() == direct.json()


def test_plugin_registry_400_propagates_through_gateway_proxy_exactly(live_stack):
    direct = httpx.get(
        f"{live_stack.registry_url}/v1/plugins/crypto/actions/get_price",
        timeout=10.0,
    )
    proxied = httpx.get(
        f"{live_stack.gateway_url}/v1/plugins/crypto/actions/get_price",
        timeout=10.0,
    )
    assert direct.status_code == 400
    assert proxied.status_code == 400
    assert proxied.json() == direct.json()


def test_rag_pipeline_404_propagates_through_gateway_proxy_exactly(live_stack):
    direct = httpx.get(
        f"{live_stack.rag_url}/knowledge-bases/does-not-exist", timeout=10.0
    )
    proxied = httpx.get(
        f"{live_stack.gateway_url}/v1/rag/knowledge-bases/does-not-exist",
        timeout=10.0,
    )
    assert direct.status_code == 404
    assert proxied.status_code == 404
    assert proxied.json() == direct.json()


def test_unreachable_downstream_surfaces_as_503_via_gateway(live_stack):
    """model-management is deliberately pointed at an unreachable dummy URL
    for this harness (#318's minimal 3-service set doesn't run it) -- a real,
    always-on trigger for routes/proxy.py's own httpx.ConnectError -> 503
    handling, not a contrived failure."""
    resp = httpx.get(f"{live_stack.gateway_url}/v1/models", timeout=10.0)
    assert resp.status_code == 503
    assert "unreachable" in resp.json()["detail"].lower()
