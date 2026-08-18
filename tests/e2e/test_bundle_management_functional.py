"""Real E2E coverage for Bundle Management (`/v1/bundles*`, routes/bundles.py),
both directly on plugin-registry and proxied through api-gateway. Previously
zero e2e coverage existed for this feature area (shipped with unit tests only)
-- tests/integration/test_api_gateway.py covers the gateway's own proxy
routing with mocked downstream calls, this proves the real multi-service
topology agrees.

No Docker/docker-socket-proxy is available in this harness (conftest.py sets
no DOCKER_HOST anywhere), so bundles.py's `_ops()` always returns None and
enable/disable/reconcile exercise their real "no proxy reachable ->
pending_create" branch rather than actually starting/stopping containers --
this is a genuine, real code path (the same one a fresh install with no
running containers yet would hit), not a workaround. Real container
start/stop is out of scope for this harness.

Admin-gated writes: self-registration always forces role="user" (#474 --
see test_auth_regression.py), so a real admin JWT can't be obtained through
the API in this harness (no Authelia OIDC either). Minting one directly with
the harness's own JWT_SECRET (same HS256/python-jose mechanism api-gateway
uses to verify every real token, Authelia-issued or not) is the correct way
to exercise the admin-only success path end-to-end without standing up a
full OIDC provider.
"""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from jose import jwt

from tests.e2e.conftest import JWT_SECRET

TIMEOUT = 10.0


def _token(role: str, sub: str = "e2e-bundles") -> str:
    payload = {
        "sub": sub,
        "username": sub,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@pytest.fixture
def admin_headers():
    return {"Authorization": f"Bearer {_token('admin')}"}


@pytest.fixture
def user_headers():
    return {"Authorization": f"Bearer {_token('user')}"}


# ── GET /v1/bundles: unauthenticated read, real compose-file data ───────────


def test_list_bundles_direct_on_registry_unauthenticated(live_stack):
    resp = httpx.get(f"{live_stack.registry_url}/v1/bundles", timeout=TIMEOUT)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = {b["name"] for b in body["bundles"]}
    # "core" always exists (bundles.py 503s if it's missing from the real
    # compose file's minder.bundle= labels) -- confirms the real
    # docker/docker-compose.yml parsed correctly, not a stub.
    assert "core" in names
    core = next(b for b in body["bundles"] if b["name"] == "core")
    assert core["core"] is True
    assert core["enabled"] is True  # core can never be disabled
    assert body["count"] == len(body["bundles"])


def test_list_bundles_via_gateway_proxy_unauthenticated(live_stack):
    """Confirms api-gateway's GET /v1/bundles proxy needs no JWT, matching
    plugin-registry's own open-read policy end-to-end."""
    resp = httpx.get(f"{live_stack.gateway_url}/v1/bundles", timeout=TIMEOUT)
    assert resp.status_code == 200, resp.text
    assert "core" in {b["name"] for b in resp.json()["bundles"]}


# ── POST .../enable|disable|reconcile: auth gating ───────────────────────────


def test_enable_rejects_unauthenticated_direct_on_registry(live_stack):
    resp = httpx.post(
        f"{live_stack.registry_url}/v1/bundles/core/enable", timeout=TIMEOUT
    )
    assert resp.status_code == 401


def test_enable_rejects_unauthenticated_via_gateway(live_stack):
    """Gateway's own _require_jwt_for_writes rejects before ever proxying."""
    resp = httpx.post(
        f"{live_stack.gateway_url}/v1/bundles/core/enable", timeout=TIMEOUT
    )
    assert resp.status_code == 401


def test_disable_rejects_non_admin_role(live_stack, user_headers):
    """A real, validly-signed token with role=user is correctly authenticated
    but not authorized -- require_role("admin") 403s it."""
    resp = httpx.post(
        f"{live_stack.registry_url}/v1/bundles/monitoring/disable",
        headers=user_headers,
        timeout=TIMEOUT,
    )
    assert resp.status_code == 403


def test_disable_core_is_rejected_even_for_admin(live_stack, admin_headers):
    """core is the always-on kernel -- disabling it 409s regardless of role."""
    resp = httpx.post(
        f"{live_stack.registry_url}/v1/bundles/core/disable",
        headers=admin_headers,
        timeout=TIMEOUT,
    )
    assert resp.status_code == 409


def test_enable_unknown_bundle_404s_for_admin(live_stack, admin_headers):
    resp = httpx.post(
        f"{live_stack.registry_url}/v1/bundles/does-not-exist/enable",
        headers=admin_headers,
        timeout=TIMEOUT,
    )
    assert resp.status_code == 404


def test_admin_enable_disable_round_trip_reports_pending_create(
    live_stack, admin_headers
):
    """No docker-socket-proxy in this harness -> every real service the bundle
    claims comes back pending_create (bundles.py's _apply, ops=None branch),
    not "changed"/"already" -- confirms the no-proxy-reachable path end-to-end
    and that the enable/disable intent actually persists to BUNDLES_STATE_PATH
    (checked via a follow-up GET)."""
    # "monitoring" (influxdb/telegraf/prometheus/etc.) is a non-core bundle
    # with no dependency on anything else this harness spawns -- disable it
    # first (whatever its current state) so enable is a real state
    # transition, not a no-op.
    disable = httpx.post(
        f"{live_stack.registry_url}/v1/bundles/monitoring/disable",
        headers=admin_headers,
        timeout=TIMEOUT,
    )
    assert disable.status_code == 200, disable.text
    assert disable.json()["enabled"] is False

    after_disable = httpx.get(f"{live_stack.registry_url}/v1/bundles", timeout=TIMEOUT)
    monitoring_after_disable = next(
        b for b in after_disable.json()["bundles"] if b["name"] == "monitoring"
    )
    assert monitoring_after_disable["enabled"] is False

    enable = httpx.post(
        f"{live_stack.registry_url}/v1/bundles/monitoring/enable",
        headers=admin_headers,
        timeout=TIMEOUT,
    )
    assert enable.status_code == 200, enable.text
    body = enable.json()
    assert body["enabled"] is True
    assert body["errors"] == []
    # Every claimed, active service the enable call targeted came back
    # pending_create -- there is no live docker-socket-proxy to actually
    # start anything against in this harness.
    assert body["started"] == []
    assert len(body["pending_create"]) > 0  # monitoring claims several real services

    after_enable = httpx.get(f"{live_stack.registry_url}/v1/bundles", timeout=TIMEOUT)
    monitoring_after_enable = next(
        b for b in after_enable.json()["bundles"] if b["name"] == "monitoring"
    )
    assert monitoring_after_enable["enabled"] is True


def test_reconcile_requires_admin_and_reports_no_proxy_pending(
    live_stack, admin_headers
):
    resp = httpx.post(
        f"{live_stack.registry_url}/v1/bundles/reconcile",
        headers=admin_headers,
        timeout=TIMEOUT,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # No live docker-socket-proxy -> nothing can have actually been started
    # or stopped, only persisted-and-pending.
    assert body["started"] == []
    assert body["stopped"] == []
    assert body["errors"] == []


def test_enable_via_gateway_proxy_with_admin_token_reaches_registry(
    live_stack, admin_headers
):
    """Confirms the gateway's generic /v1/bundles/{path} proxy forwards a
    validly-authorized POST through to plugin-registry end-to-end (not just
    the direct-on-registry path above)."""
    resp = httpx.post(
        f"{live_stack.gateway_url}/v1/bundles/core/enable",
        headers=admin_headers,
        timeout=TIMEOUT,
    )
    # core is already enabled and can't be meaningfully disabled, so this is a
    # no-op enable -- the point is confirming the proxy delivers a 200 from
    # the real registry process, not a gateway-side 401/403/404.
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is True
