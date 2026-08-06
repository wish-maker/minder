"""Unit tests for plugin-registry's ProxyRouter error handling (#357).

#357: forward_request/health_check_proxy's generic `except Exception` catch-all
returned HTTPException(500/503, detail=f"...: {str(e)}") -- leaking the raw
exception string. Switched to shared.errors.backend_http_error, matching the
explicit httpx.ConnectError/httpx.TimeoutException branches already above it
(which stay untouched -- they already give clean, sanitized messages).

Loaded via sys.path + a stale-cache clear, matching this session's
established precedent for plugin-registry tests.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

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


@pytest.mark.asyncio
async def test_forward_request_generic_failure_does_not_leak_exception_text(
    monkeypatch,
):
    secret_looking = "internal-db-password=hunter2"
    router = proxy.ProxyRouter(
        services_db={"crypto": SimpleNamespace(host="crypto", port=9000)}
    )

    class _BoomClient:
        async def request(self, **kwargs):
            raise RuntimeError(secret_looking)

    async def _fake_get_client():
        return _BoomClient()

    monkeypatch.setattr(router, "get_http_client", _fake_get_client)

    with pytest.raises(Exception) as exc_info:
        await router.forward_request("crypto", "/some/path", _FakeRequest())

    assert exc_info.value.status_code == 500
    assert secret_looking not in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_health_check_proxy_generic_failure_does_not_leak_exception_text(
    monkeypatch,
):
    secret_looking = "internal-db-password=hunter2"
    router = proxy.ProxyRouter(
        services_db={
            "crypto": SimpleNamespace(
                host="crypto", port=9000, health_check_url="/health"
            )
        }
    )

    class _BoomClient:
        async def get(self, *a, **k):
            raise RuntimeError(secret_looking)

    async def _fake_get_client():
        return _BoomClient()

    monkeypatch.setattr(router, "get_http_client", _fake_get_client)

    with pytest.raises(Exception) as exc_info:
        await router.health_check_proxy("crypto")

    # A plain RuntimeError isn't a connectivity-shaped failure -- backend_http_error
    # correctly falls back to a generic sanitized 500, not 503.
    assert exc_info.value.status_code == 500
    assert secret_looking not in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_health_check_proxy_connect_error_stays_a_clean_503(monkeypatch):
    """The explicit httpx.ConnectError branch above the generic catch-all must
    keep working unchanged -- this test guards against accidentally routing it
    into the generic path instead."""
    import httpx

    router = proxy.ProxyRouter(
        services_db={
            "crypto": SimpleNamespace(
                host="crypto", port=9000, health_check_url="/health"
            )
        }
    )

    class _BoomClient:
        async def get(self, *a, **k):
            raise httpx.ConnectError("connection refused")

    async def _fake_get_client():
        return _BoomClient()

    monkeypatch.setattr(router, "get_http_client", _fake_get_client)

    with pytest.raises(Exception) as exc_info:
        await router.health_check_proxy("crypto")

    assert exc_info.value.status_code == 503
    assert "unreachable" in exc_info.value.detail
