"""Real E2E coverage for the Status page's backend: api-gateway's `GET
/v1/status` fleet fan-out (routes/health.py) and plugin-registry's `GET
/v1/containers/{name}/logs` (routes/containers.py). Previously zero e2e
coverage existed for either (shipped with unit tests only).

`/v1/status` needs no Docker at all -- it just fans out to each configured
service's own real `/health` over HTTP. This harness spawns api-gateway,
plugin-registry, marketplace, rag-pipeline, model-management, and graph-rag
as real processes, but NOT plugin-state-manager or tts-stt, and api-gateway's
own default `API_GATEWAY_URL` is a container hostname that doesn't resolve
here either -- so a real, unmodified run of this endpoint against the harness
produces a genuine mix of reachable/unreachable services, exercising both of
`_probe_fleet_service`'s branches without any conftest.py changes.

`/v1/containers/.../logs` DOES hard-require a real docker-socket-proxy
(DOCKER_HOST), which this harness never sets -- so the real container-log
content itself is out of scope here (covered by unit tests mocking the proxy
response). What's still genuinely end-to-end testable without Docker: JWT
gating (get_current_user), the fixed-allowlist 404 for an unknown service
name, and the real 503 `_docker_base_url()` produces when DOCKER_HOST is
unset -- all real code paths a bare/partially-degraded install can actually
hit, not synthetic.
"""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from jose import jwt

from tests.e2e.conftest import JWT_SECRET

TIMEOUT = 10.0

_HARNESS_SERVICES = {
    "plugin-registry",
    "marketplace",
    "rag-pipeline",
    "model-management",
    "graph-rag",
}
_NOT_IN_HARNESS = {"api-gateway", "plugin-state-manager", "tts-stt"}


@pytest.fixture
def user_token():
    payload = {
        "sub": "e2e-status",
        "username": "e2e-status",
        "role": "user",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


# ── GET /v1/status ────────────────────────────────────────────────────────


def test_fleet_status_reports_every_configured_service(live_stack):
    resp = httpx.get(f"{live_stack.gateway_url}/v1/status", timeout=TIMEOUT)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = {s["name"] for s in body["services"]}
    # All 8 fleet entries are always reported, reachable or not -- this is a
    # fan-out over a fixed list, never a partial result.
    assert names == _HARNESS_SERVICES | _NOT_IN_HARNESS


def test_fleet_status_marks_real_running_services_reachable(live_stack):
    resp = httpx.get(f"{live_stack.gateway_url}/v1/status", timeout=TIMEOUT)
    by_name = {s["name"]: s for s in resp.json()["services"]}
    for name in _HARNESS_SERVICES:
        entry = by_name[name]
        assert entry["reachable"] is True, f"{name}: {entry}"
        # "status" reflects that service's OWN real dependency health (e.g.
        # graph-rag reports "unhealthy" if Neo4j genuinely isn't reachable in
        # this environment, "healthy"/"degraded" otherwise) -- reachable is
        # what this test actually guarantees; the exact status string is real
        # downstream state, not something to pin to one value.
        assert entry["status"] != "unreachable", f"{name}: {entry}"
        # Each service's own real /health body is forwarded verbatim -- these
        # keys only exist on a genuinely successful, parsed response.
        assert "environment" in entry


def test_fleet_status_marks_services_outside_the_harness_unreachable(live_stack):
    """plugin-state-manager and tts-stt aren't spawned by this harness, and
    api-gateway's own default API_GATEWAY_URL is a container hostname that
    doesn't resolve to itself here either -- all three must fail closed
    (reachable: false), never raise and 500 the whole endpoint."""
    resp = httpx.get(f"{live_stack.gateway_url}/v1/status", timeout=TIMEOUT)
    by_name = {s["name"]: s for s in resp.json()["services"]}
    for name in _NOT_IN_HARNESS:
        entry = by_name[name]
        assert entry["reachable"] is False, f"{name}: {entry}"
        assert entry["status"] == "unreachable"
        assert "error" in entry


# ── GET /v1/containers/{name}/logs ───────────────────────────────────────


def test_container_logs_rejects_unauthenticated_direct_on_registry(live_stack):
    resp = httpx.get(
        f"{live_stack.registry_url}/v1/containers/api-gateway/logs", timeout=TIMEOUT
    )
    assert resp.status_code == 401


def test_container_logs_rejects_unauthenticated_via_gateway_proxy(live_stack):
    resp = httpx.get(
        f"{live_stack.gateway_url}/v1/containers/api-gateway/logs", timeout=TIMEOUT
    )
    assert resp.status_code == 401


def test_container_logs_unknown_service_name_404s(live_stack, user_token):
    """Fixed allowlist (_KNOWN_SERVICES), not a caller-controlled name fed
    straight into a container-name lookup -- even a validly-authenticated
    caller can't probe an arbitrary name."""
    resp = httpx.get(
        f"{live_stack.registry_url}/v1/containers/not-a-real-service/logs",
        headers={"Authorization": f"Bearer {user_token}"},
        timeout=TIMEOUT,
    )
    assert resp.status_code == 404


def test_container_logs_known_service_503s_with_no_docker_proxy(live_stack, user_token):
    """No DOCKER_HOST anywhere in this harness -> _docker_base_url() is empty
    -> the real "docker-socket-proxy unreachable" 503, not a crash or a
    silent empty-logs response."""
    resp = httpx.get(
        f"{live_stack.registry_url}/v1/containers/api-gateway/logs",
        headers={"Authorization": f"Bearer {user_token}"},
        timeout=TIMEOUT,
    )
    assert resp.status_code == 503
    assert "docker-socket-proxy" in resp.json()["detail"]


def test_container_logs_via_gateway_proxy_reaches_registry(live_stack, user_token):
    """Confirms api-gateway's GET /v1/containers/{path} proxy forwards a
    validly-authenticated request through to plugin-registry end-to-end
    (same 503-no-proxy outcome as calling the registry directly, not a
    gateway-side auth/routing failure)."""
    resp = httpx.get(
        f"{live_stack.gateway_url}/v1/containers/api-gateway/logs",
        headers={"Authorization": f"Bearer {user_token}"},
        timeout=TIMEOUT,
    )
    assert resp.status_code == 503
    assert "docker-socket-proxy" in resp.json()["detail"]
