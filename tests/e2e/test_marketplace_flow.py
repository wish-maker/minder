"""Real E2E coverage for the marketplace install/uninstall/enable/disable
flow, through api-gateway's real proxy to a real marketplace process (#437).

Closes the gap that let a real bug ship (#436): `tests/integration/
test_marketplace_gateway_functional.py` looks identical to this file but
always SKIPPED in CI (no live network-reachable stack in that job) --
nothing ever actually exercised install/uninstall/enable/disable against a
live gateway+marketplace pair until this file. Neo4j-backed `/v1/graph/*`
routes are out of scope here (see conftest.py's docstring) -- this covers
the Postgres-only paths that had the actual bugs.
"""

import uuid

import httpx
import pytest


@pytest.fixture(scope="module")
def auth_token(live_stack):
    """Register + log in a throwaway user through the REAL gateway -- no
    shortcut JWT construction, so this also proves auth/register/login work
    against a real Postgres-backed users table in this harness."""
    username = "e2e-marketplace-user"
    password = "TestPass123!"
    httpx.post(
        f"{live_stack.gateway_url}/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
        },
        timeout=15.0,
    )
    r = httpx.post(
        f"{live_stack.gateway_url}/v1/auth/login",
        json={"username": username, "password": password},
        timeout=15.0,
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def plugin_id(live_stack, auth_token):
    """A fresh marketplace plugin listing, created through the real gateway."""
    r = httpx.post(
        f"{live_stack.gateway_url}/v1/marketplace/plugins",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "name": f"e2e-test-plugin-{uuid.uuid4()}",
            "display_name": "E2E Test Plugin",
            "description": "Created by test_marketplace_flow.py",
            "author": "E2E Test",
        },
        timeout=15.0,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_list_plugins_through_gateway(live_stack):
    r = httpx.get(f"{live_stack.gateway_url}/v1/marketplace/plugins", timeout=10.0)
    assert r.status_code == 200, r.text
    assert "plugins" in r.json()


def test_install_plugin_succeeds(live_stack, plugin_id, auth_token):
    """Regression test for #434/#436: install used to 500 for every real
    user (dead FK to marketplace_users, then a UUID-vs-str serialization
    bug on plugin_id) -- both bugs only manifest with a REAL asyncpg
    round-trip, which this test (unlike the always-skipped integration
    version) actually performs."""
    r = httpx.post(
        f"{live_stack.gateway_url}/v1/marketplace/plugins/{plugin_id}/install",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=15.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plugin_id"] == plugin_id
    assert body["status"] == "installed"
    assert body["enabled"] is True


def test_reinstall_already_installed_succeeds(live_stack, plugin_id, auth_token):
    """The "already installed" branch of install_plugin had the identical
    plugin_id serialization bug, independent of the create-new-row branch."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    httpx.post(
        f"{live_stack.gateway_url}/v1/marketplace/plugins/{plugin_id}/install",
        headers=headers,
        timeout=15.0,
    )
    r = httpx.post(
        f"{live_stack.gateway_url}/v1/marketplace/plugins/{plugin_id}/install",
        headers=headers,
        timeout=15.0,
    )
    assert r.status_code == 200, r.text
    assert r.json()["plugin_id"] == plugin_id


def test_installed_plugin_appears_in_my_installations(
    live_stack, plugin_id, auth_token
):
    headers = {"Authorization": f"Bearer {auth_token}"}
    httpx.post(
        f"{live_stack.gateway_url}/v1/marketplace/plugins/{plugin_id}/install",
        headers=headers,
        timeout=15.0,
    )
    r = httpx.get(
        f"{live_stack.gateway_url}/v1/marketplace/installations/me",
        headers=headers,
        timeout=10.0,
    )
    assert r.status_code == 200, r.text
    matches = [i for i in r.json()["installations"] if i["plugin_id"] == plugin_id]
    assert len(matches) == 1, r.json()
    assert matches[0]["display_name"] == "E2E Test Plugin"


def test_disable_then_enable_round_trip(live_stack, plugin_id, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    httpx.post(
        f"{live_stack.gateway_url}/v1/marketplace/plugins/{plugin_id}/install",
        headers=headers,
        timeout=15.0,
    )
    d = httpx.post(
        f"{live_stack.gateway_url}/v1/marketplace/plugins/{plugin_id}/disable",
        headers=headers,
        timeout=15.0,
    )
    assert d.status_code == 200, d.text
    assert d.json()["status"] == "disabled"

    e = httpx.post(
        f"{live_stack.gateway_url}/v1/marketplace/plugins/{plugin_id}/enable",
        headers=headers,
        timeout=15.0,
    )
    assert e.status_code == 200, e.text
    assert e.json()["status"] == "enabled"


def test_uninstall_removes_it_from_my_installations(live_stack, plugin_id, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    httpx.post(
        f"{live_stack.gateway_url}/v1/marketplace/plugins/{plugin_id}/install",
        headers=headers,
        timeout=15.0,
    )
    d = httpx.delete(
        f"{live_stack.gateway_url}/v1/marketplace/plugins/{plugin_id}/uninstall",
        headers=headers,
        timeout=15.0,
    )
    assert d.status_code == 200, d.text

    r = httpx.get(
        f"{live_stack.gateway_url}/v1/marketplace/installations/me",
        headers=headers,
        timeout=10.0,
    )
    assert plugin_id not in [i["plugin_id"] for i in r.json()["installations"]]


def test_activate_license_succeeds_for_a_real_user(live_stack, plugin_id, auth_token):
    """Regression test for the identical #434 dead-FK bug, missed on
    marketplace_licenses when it was fixed for marketplace_installations:
    POST /v1/marketplace/licenses/activate 500'd for every real user_id
    (only the seeded "admin" row satisfied the now-dropped FK to the dead
    marketplace_users table). Only manifests with a real asyncpg round-trip,
    which this E2E test (unlike a mocked unit test) actually performs."""
    r = httpx.post(
        f"{live_stack.gateway_url}/v1/marketplace/licenses/activate",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"plugin_id": plugin_id, "tier": "pro"},
        timeout=15.0,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "activated"
    assert r.json()["license"]["plugin_id"] == plugin_id


def test_activated_license_is_listed_for_the_user(live_stack, plugin_id, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    httpx.post(
        f"{live_stack.gateway_url}/v1/marketplace/licenses/activate",
        headers=headers,
        json={"plugin_id": plugin_id, "tier": "pro"},
        timeout=15.0,
    )
    r = httpx.get(
        f"{live_stack.gateway_url}/v1/marketplace/licenses",
        headers=headers,
        timeout=10.0,
    )
    assert r.status_code == 200, r.text
    matches = [lic for lic in r.json()["licenses"] if lic["plugin_id"] == plugin_id]
    assert len(matches) == 1, r.json()


def test_my_installations_requires_auth(live_stack):
    r = httpx.get(
        f"{live_stack.gateway_url}/v1/marketplace/installations/me", timeout=10.0
    )
    assert r.status_code == 401
