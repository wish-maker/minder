"""Unit tests for api-gateway proxy response-header hygiene (#211 MED).

The proxy rebuilds the body from ``response.json()``, so copying the downstream's
``content-length``/``content-encoding`` (and hop-by-hop headers) onto the new
response is wrong — a downstream that gzips would make the client receive
``content-encoding: gzip`` on a plaintext body plus a mismatched length. These lock
that those headers are stripped while normal headers pass through.

api-gateway is a hyphenated service dir; ``proxy`` imports ``core.auth`` /
``core.clients`` at module top. Fakes are injected into ``sys.modules`` and restored
so another service's ``core`` package isn't poisoned (the #142 gotcha).
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest

_ROUTE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "api-gateway"
    / "routes"
    / "proxy.py"
)


@pytest.fixture
def proxy_mod():
    names = ("core", "core.auth", "core.clients")
    saved = {n: sys.modules.get(n) for n in names}
    for n in names:
        sys.modules[n] = ModuleType(n)
    sys.modules["core.auth"].verify_jwt_token = lambda t: {"sub": "x"}
    sys.modules["core.clients"].SERVICE_REGISTRY = {}
    sys.modules["core.clients"].http_client = None
    try:
        spec = importlib.util.spec_from_file_location("gw_proxy_route", _ROUTE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        for n, m in saved.items():
            if m is not None:
                sys.modules[n] = m
            else:
                sys.modules.pop(n, None)


def test_strips_content_framing_and_hop_by_hop(proxy_mod):
    headers = httpx.Headers(
        {
            "content-type": "application/json",
            "content-length": "999",
            "content-encoding": "gzip",
            "Transfer-Encoding": "chunked",
            "Connection": "keep-alive",
        }
    )
    out = proxy_mod._safe_response_headers(headers)
    assert out == {"content-type": "application/json"}


def test_keeps_normal_headers(proxy_mod):
    headers = httpx.Headers(
        {
            "content-type": "application/json",
            "x-request-id": "abc",
            "cache-control": "no-store",
        }
    )
    out = proxy_mod._safe_response_headers(headers)
    assert out == {
        "content-type": "application/json",
        "x-request-id": "abc",
        "cache-control": "no-store",
    }
