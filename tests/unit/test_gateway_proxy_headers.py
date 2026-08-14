"""Unit tests for api-gateway proxy response-header hygiene (#211 MED) and
binary-body passthrough (Status/Voice pages).

The proxy rebuilds the body from ``response.json()``, so copying the downstream's
``content-length``/``content-encoding`` (and hop-by-hop headers) onto the new
response is wrong — a downstream that gzips would make the client receive
``content-encoding: gzip`` on a plaintext body plus a mismatched length. These lock
that those headers are stripped while normal headers pass through.

``proxy_request`` also can't force EVERY downstream body through ``response.json()``
— tts-stt's ``POST /v1/tts`` returns binary WAV/MP3 audio, which would raise inside
the broad ``except Exception`` and surface as a misleading 500 "Internal proxy
error" instead of the actual audio. The non-JSON branch added for this is tested
below with a fake ``http_client``.

api-gateway is a hyphenated service dir; ``proxy`` imports ``core.auth`` /
``core.clients`` at module top. Fakes are injected into ``sys.modules`` and restored
so another service's ``core`` package isn't poisoned (the #142 gotcha).

``proxy`` also does a bare ``from config import settings`` -- "config" is just as
collision-prone as "core"/"routes" (conftest.py's own #333 gotcha note), and unlike
core.auth/core.clients it can't just be stubbed out: ``settings.MAX_PROXY_BODY_SIZE_MB``
has to be a real value for ``_read_body_capped`` to do anything. So this loads
api-gateway's own config.py fresh from its file (not a bare ``import config``, which
would resolve via whatever service directory another test left earliest on
sys.path) and registers *that* under "config" for the duration of the test.
"""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import httpx
import pytest

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "api-gateway"
_ROUTE = _SERVICE_DIR / "routes" / "proxy.py"
_CONFIG = _SERVICE_DIR / "config.py"


@pytest.fixture
def proxy_mod():
    names = ("core", "core.auth", "core.clients", "config")
    saved = {n: sys.modules.get(n) for n in names}
    for n in names:
        sys.modules[n] = ModuleType(n)
    sys.modules["core.auth"].verify_jwt_token = lambda t: {"sub": "x"}
    sys.modules["core.clients"].SERVICE_REGISTRY = {}
    sys.modules["core.clients"].http_client = None
    config_spec = importlib.util.spec_from_file_location("config", _CONFIG)
    config_mod = importlib.util.module_from_spec(config_spec)
    sys.modules["config"] = config_mod
    config_spec.loader.exec_module(config_mod)
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


class _FakeRequest:
    """Duck-typed stand-in for FastAPI's Request -- proxy_request only reads
    body()/headers/client.host/state.request_id/method/query_params, so a real
    ASGI Request isn't needed."""

    def __init__(self, method="GET", body=b""):
        self.method = method
        self.headers = {"authorization": "Bearer x"}
        self.client = SimpleNamespace(host="127.0.0.1")
        self.state = SimpleNamespace(request_id="test-req-id")
        self.query_params = {}
        self._body = body

    async def body(self):
        return self._body

    async def stream(self):
        # A single chunk is enough for these tests; real ASGI streams split
        # large bodies across many, but _read_body_capped only cares about
        # the running total, not chunk boundaries.
        if self._body:
            yield self._body


class _FakeHTTPClient:
    def __init__(self, response):
        self._response = response

    async def request(self, **kwargs):
        return self._response


def test_binary_response_passes_through_raw(proxy_mod):
    """A non-JSON downstream body (tts-stt's synthesized WAV/MP3 audio) must be
    returned as-is, not forced through response.json() -- that would raise and
    surface as a misleading 500 instead of the actual audio."""
    audio_bytes = b"RIFF....WAVEfmt "
    fake_response = SimpleNamespace(
        status_code=200,
        content=audio_bytes,
        headers=httpx.Headers({"content-type": "audio/wav", "content-length": "999"}),
        json=lambda: (_ for _ in ()).throw(ValueError("not JSON")),
    )
    proxy_mod.http_client = _FakeHTTPClient(fake_response)

    result = asyncio.run(
        proxy_mod.proxy_request("http://tts-stt:8006", "v1/tts", _FakeRequest("POST"))
    )

    assert result.status_code == 200
    assert result.body == audio_bytes
    assert result.media_type == "audio/wav"
    # _safe_response_headers strips the downstream's stale content-length
    # (999, for the un-transformed body) -- Starlette computes its own from
    # the actual bytes when the Response is rendered.
    assert result.headers.get("content-length") != "999"


def test_read_body_capped_passes_body_within_limit(proxy_mod):
    body = asyncio.run(
        proxy_mod._read_body_capped(_FakeRequest(body=b"hello"), max_bytes=10)
    )
    assert body == b"hello"


def test_read_body_capped_rejects_body_over_limit(proxy_mod):
    """The gateway must reject an oversized upload with 413 *before* the full
    body is ever fully buffered -- an unbounded `request.body()` call would
    exhaust gateway memory on a large/malicious upload regardless of what any
    downstream service's own size limit enforces (that check only runs after
    the gateway already buffered everything)."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            proxy_mod._read_body_capped(_FakeRequest(body=b"x" * 11), max_bytes=10)
        )
    assert exc.value.status_code == 413


def test_json_response_still_decoded_and_rewrapped(proxy_mod):
    """A normal JSON downstream body keeps the existing decode-and-rewrap
    behavior (unaffected by the new binary branch)."""
    fake_response = SimpleNamespace(
        status_code=200,
        content=b'{"ok": true}',
        headers=httpx.Headers({"content-type": "application/json"}),
        json=lambda: {"ok": True},
    )
    proxy_mod.http_client = _FakeHTTPClient(fake_response)

    result = asyncio.run(
        proxy_mod.proxy_request(
            "http://plugin-registry:8001", "v1/plugins", _FakeRequest()
        )
    )

    assert result.status_code == 200
    assert json.loads(result.body) == {"ok": True}
