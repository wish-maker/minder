"""Functional tests for the marketplace service AS REACHED THROUGH THE GATEWAY,
run against the real live-process harness (`live_stack`, #437 -- moved here
from tests/integration/ so these actually execute in CI instead of silently
skipping for lack of a network-reachable service).

Regression coverage for three real, live-breaking bugs found while planning a
browser UI for the marketplace (#402):

1. api-gateway had NO proxy route for /v1/marketplace/* or /v1/graph/* at
   all -- every other service the client talks to has one, marketplace didn't.
2. marketplace_installations.user_id had a live FK to marketplace_users, a
   table nothing ever inserts into except one seed row ("admin") -- any real
   user's install threw an unhandled ForeignKeyViolationError (500).
3. InstallationResponse.user_id had a UUID-only regex pattern, but real
   values are str(user["id"]) from the JWT `sub` (e.g. "4") -- even after
   fixing bug 2, install's response_model would still 500 on serialization.

Every assertion here goes through the gateway (not marketplace's own port) --
per this session's own recent lesson (#433), a fix verified only against a
service's direct port can still be broken for real clients if the gateway
proxy itself is what's wrong.
"""

import os
import uuid

import httpx
import pytest


@pytest.fixture
def auth_token(live_stack):
    """A JWT for the marketplace write endpoints, all proxied through the
    gateway (same pattern as test_rag_pipeline_functional.py's auth_token)."""
    username = f"mkttest-{os.getpid()}"
    password = "TestPass123!"
    httpx.post(
        f"{live_stack.gateway_url}/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
        },
        timeout=20.0,
    )
    r = httpx.post(
        f"{live_stack.gateway_url}/v1/auth/login",
        json={"username": username, "password": password},
        timeout=20.0,
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def plugin_id(live_stack, auth_token):
    """A fresh marketplace plugin listing, created THROUGH THE GATEWAY.

    Function-scoped -- every test that uses this gets its OWN plugin, so
    `name` must be unique per call, not just per process: `os.getpid()` alone
    collided across the 3 tests in this file that all request this fixture
    within the same pytest run, 500ing on marketplace's real unique
    constraint on `name` (masked until now by #437 -- this file never
    actually executed before).
    """
    r = httpx.post(
        f"{live_stack.gateway_url}/v1/marketplace/plugins",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "name": f"test-mkt-plugin-{os.getpid()}-{uuid.uuid4().hex[:8]}",
            "display_name": "Test Marketplace Plugin",
            "description": "Created by test_marketplace_gateway_functional.py",
            "author": "Integration Test",
        },
        timeout=20.0,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_list_plugins_reachable_through_gateway(live_stack):
    # Regression test for bug 1: this 404'd with zero proxy route registered.
    r = httpx.get(f"{live_stack.gateway_url}/v1/marketplace/plugins", timeout=10.0)
    assert r.status_code == 200, r.text
    assert "plugins" in r.json()


def test_graph_health_reachable_through_gateway(live_stack):
    # /v1/graph is a SEPARATE route namespace from /v1/marketplace -- needs
    # its own proxy route, not covered by fixing bug 1 alone.
    r = httpx.get(f"{live_stack.gateway_url}/v1/graph/health", timeout=10.0)
    assert r.status_code == 200, r.text


def test_install_plugin_does_not_500(live_stack, plugin_id, auth_token):
    # Regression test for bugs 2 + 3: this used to throw an unhandled
    # ForeignKeyViolationError, then (after fixing that) a ResponseValidationError
    # on user_id -- both manifesting as a 500 to any real user clicking Install.
    r = httpx.post(
        f"{live_stack.gateway_url}/v1/marketplace/plugins/{plugin_id}/install",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=20.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plugin_id"] == plugin_id
    assert body["status"] == "installed"
    assert body["enabled"] is True


def test_installed_plugin_appears_in_my_installations(
    live_stack, plugin_id, auth_token
):
    httpx.post(
        f"{live_stack.gateway_url}/v1/marketplace/plugins/{plugin_id}/install",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=20.0,
    )

    r = httpx.get(
        f"{live_stack.gateway_url}/v1/marketplace/installations/me",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=10.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    matches = [i for i in body["installations"] if i["plugin_id"] == plugin_id]
    assert len(matches) == 1, body
    assert matches[0]["name"]
    assert matches[0]["display_name"] == "Test Marketplace Plugin"


def test_uninstall_removes_it_from_my_installations(live_stack, plugin_id, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    httpx.post(
        f"{live_stack.gateway_url}/v1/marketplace/plugins/{plugin_id}/install",
        headers=headers,
        timeout=20.0,
    )

    d = httpx.delete(
        f"{live_stack.gateway_url}/v1/marketplace/plugins/{plugin_id}/uninstall",
        headers=headers,
        timeout=20.0,
    )
    assert d.status_code == 200, d.text

    r = httpx.get(
        f"{live_stack.gateway_url}/v1/marketplace/installations/me",
        headers=headers,
        timeout=10.0,
    )
    assert r.status_code == 200, r.text
    assert plugin_id not in [i["plugin_id"] for i in r.json()["installations"]]


def test_my_installations_requires_auth(live_stack):
    r = httpx.get(
        f"{live_stack.gateway_url}/v1/marketplace/installations/me", timeout=10.0
    )
    assert r.status_code == 401
