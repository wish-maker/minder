"""Unit tests filling ProxyRouter's remaining coverage gaps (72%).

test_plugin_registry_proxy_error_handling.py already locks in the generic-
exception-doesn't-leak-text fix (#357) and the ConnectError-stays-503 guard
for health_check_proxy. This adds everything else: get_http_client's lazy-
create/reuse lifecycle, forward_request's service-not-found 404 + successful
response passthrough + ConnectError/TimeoutException branches,
health_check_proxy's service-not-found 404 + non-200-status branch +
TimeoutException branch, and close().

Same isolated-import pattern as the sibling suite.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

_SERVICE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "plugin-registry"
)

_COLLISION_PRONE_NAMES = ("core", "routes", "models")


def _isolated_import(module_path: str):
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)
    sys.path.insert(0, str(_SERVICE_DIR))
    import importlib

    try:
        return importlib.import_module(module_path)
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


proxy = _isolated_import("routes.proxy")


class _FakeRequest:
    method = "GET"
    headers = {}
    query_params = {}

    async def body(self):
        return b""


def _router(**service_kwargs):
    defaults = {"host": "crypto", "port": 9000, "health_check_url": "/health"}
    defaults.update(service_kwargs)
    return proxy.ProxyRouter(services_db={"crypto": SimpleNamespace(**defaults)})


# --- get_http_client lifecycle ------------------------------------------------


@pytest.mark.asyncio
async def test_get_http_client_creates_once_and_reuses():
    router = _router()
    assert router.http_client is None

    client1 = await router.get_http_client()
    client2 = await router.get_http_client()

    assert client1 is client2
    assert router.http_client is client1
    await router.close()


@pytest.mark.asyncio
async def test_close_resets_the_client_to_none():
    router = _router()
    await router.get_http_client()
    assert router.http_client is not None

    await router.close()

    assert router.http_client is None


@pytest.mark.asyncio
async def test_close_is_a_noop_when_never_created():
    router = _router()
    await router.close()  # must not raise
    assert router.http_client is None


# --- forward_request -----------------------------------------------------------


@pytest.mark.asyncio
async def test_forward_request_404_when_service_not_registered():
    router = _router()

    with pytest.raises(Exception) as exc_info:
        await router.forward_request("unknown-service", "/x", _FakeRequest())

    assert exc_info.value.status_code == 404


class _FakeUpstreamResponse:
    def __init__(self, status_code=200, content=b'{"ok": true}', headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {"content-type": "application/json"}


@pytest.mark.asyncio
async def test_forward_request_returns_the_upstream_response_verbatim(monkeypatch):
    router = _router()
    captured = {}

    class _FakeClient:
        async def request(self, **kwargs):
            captured.update(kwargs)
            return _FakeUpstreamResponse()

    async def fake_get_client():
        return _FakeClient()

    monkeypatch.setattr(router, "get_http_client", fake_get_client)

    response = await router.forward_request("crypto", "/get_price", _FakeRequest())

    assert response.status_code == 200
    assert response.body == b'{"ok": true}'
    assert captured["url"] == "http://crypto:9000/get_price"
    assert captured["method"] == "GET"
    # Hop-by-hop headers stripped before forwarding.
    assert "host" not in captured["headers"]
    assert "connection" not in captured["headers"]


@pytest.mark.asyncio
async def test_forward_request_connect_error_becomes_a_clean_503(monkeypatch):
    router = _router()

    class _BoomClient:
        async def request(self, **kwargs):
            raise httpx.ConnectError("connection refused")

    async def fake_get_client():
        return _BoomClient()

    monkeypatch.setattr(router, "get_http_client", fake_get_client)

    with pytest.raises(Exception) as exc_info:
        await router.forward_request("crypto", "/x", _FakeRequest())

    assert exc_info.value.status_code == 503
    assert "connection failed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_forward_request_timeout_becomes_a_clean_504(monkeypatch):
    router = _router()

    class _SlowClient:
        async def request(self, **kwargs):
            raise httpx.TimeoutException("timed out")

    async def fake_get_client():
        return _SlowClient()

    monkeypatch.setattr(router, "get_http_client", fake_get_client)

    with pytest.raises(Exception) as exc_info:
        await router.forward_request("crypto", "/x", _FakeRequest())

    assert exc_info.value.status_code == 504
    assert "timeout" in exc_info.value.detail


# --- health_check_proxy --------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_proxy_404_when_service_not_registered():
    router = _router()

    with pytest.raises(Exception) as exc_info:
        await router.health_check_proxy("unknown-service")

    assert exc_info.value.status_code == 404


class _FakeHealthResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_health_check_proxy_returns_json_when_healthy(monkeypatch):
    router = _router()

    class _FakeClient:
        async def get(self, url, timeout=None):
            return _FakeHealthResponse(200, {"status": "ok"})

    async def fake_get_client():
        return _FakeClient()

    monkeypatch.setattr(router, "get_http_client", fake_get_client)

    result = await router.health_check_proxy("crypto")

    assert result == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_check_proxy_raises_503_on_non_200_status(monkeypatch):
    router = _router()

    class _FakeUnhealthyResponse:
        status_code = 500

    class _FakeClient:
        async def get(self, url, timeout=None):
            return _FakeUnhealthyResponse()

    async def fake_get_client():
        return _FakeClient()

    monkeypatch.setattr(router, "get_http_client", fake_get_client)

    with pytest.raises(Exception) as exc_info:
        await router.health_check_proxy("crypto")

    assert exc_info.value.status_code == 503
    assert "unhealthy" in exc_info.value.detail


@pytest.mark.asyncio
async def test_health_check_proxy_timeout_becomes_a_clean_504(monkeypatch):
    router = _router()

    class _SlowClient:
        async def get(self, url, timeout=None):
            raise httpx.TimeoutException("timed out")

    async def fake_get_client():
        return _SlowClient()

    monkeypatch.setattr(router, "get_http_client", fake_get_client)

    with pytest.raises(Exception) as exc_info:
        await router.health_check_proxy("crypto")

    assert exc_info.value.status_code == 504
    assert "timeout" in exc_info.value.detail
