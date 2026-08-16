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
from starlette.datastructures import QueryParams

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

    def __init__(self, method="GET", body=b"", headers=None, query_params=None):
        self.method = method
        self.headers = headers if headers is not None else {"authorization": "Bearer x"}
        self.client = SimpleNamespace(host="127.0.0.1")
        self.state = SimpleNamespace(request_id="test-req-id")
        self.query_params = (
            query_params if query_params is not None else QueryParams("")
        )
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
        self.captured_kwargs = None

    async def request(self, **kwargs):
        self.captured_kwargs = kwargs
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


def _json_fake_response():
    return SimpleNamespace(
        status_code=200,
        content=b'{"ok": true}',
        headers=httpx.Headers({"content-type": "application/json"}),
        json=lambda: {"ok": True},
    )


def test_outbound_request_strips_hop_by_hop_and_content_length(proxy_mod):
    """Found in a background audit: the outbound (request-side) header build
    only ever popped "host"/"connection", leaving "transfer-encoding" (and the
    rest of the hop-by-hop set) to pass straight through. A chunk-encoded
    inbound request has no Content-Length of its own -- httpx then auto-adds
    ITS OWN Content-Length (computed from the fully-buffered body) alongside
    the still-present, now-stale "transfer-encoding: chunked", producing a
    Content-Length + Transfer-Encoding conflict on the wire (RFC 7230 §3.3.3;
    the classic request-smuggling primitive). Confirm every hop-by-hop header
    plus content-length is gone from what's actually handed to httpx."""
    fake_client = _FakeHTTPClient(_json_fake_response())
    proxy_mod.http_client = fake_client

    inbound_headers = {
        "authorization": "Bearer x",
        "transfer-encoding": "chunked",
        "connection": "keep-alive",
        "content-length": "999",
        "host": "gateway.internal",
        "x-custom": "keep-me",
    }
    asyncio.run(
        proxy_mod.proxy_request(
            "http://rag-pipeline:8003",
            "v1/rag/ingest",
            _FakeRequest("POST", body=b'{"a":1}', headers=inbound_headers),
        )
    )

    sent_headers = fake_client.captured_kwargs["headers"]
    for stripped in (
        "transfer-encoding",
        "connection",
        "content-length",
        "host",
    ):
        assert stripped not in sent_headers
    assert sent_headers["x-custom"] == "keep-me"
    assert sent_headers["authorization"] == "Bearer x"


def test_outbound_request_preserves_repeated_query_params(proxy_mod):
    """Found in the same audit: passing request.query_params (a Starlette
    QueryParams) directly to httpx.request(params=...) silently collapses
    repeated keys to their last value -- httpx.QueryParams' constructor falls
    into a generic-Mapping code path that calls .items() (last-value-wins),
    not the multidict-aware .multi_items(). Confirm all three "tag" values
    survive into what's actually sent to httpx."""
    fake_client = _FakeHTTPClient(_json_fake_response())
    proxy_mod.http_client = fake_client

    request = _FakeRequest(query_params=QueryParams("tag=a&tag=b&tag=c&x=1"))
    asyncio.run(
        proxy_mod.proxy_request("http://plugin-registry:8001", "v1/plugins", request)
    )

    sent_params = list(fake_client.captured_kwargs["params"])
    assert sent_params.count(("tag", "a")) == 1
    assert sent_params.count(("tag", "b")) == 1
    assert sent_params.count(("tag", "c")) == 1
    assert ("x", "1") in sent_params


def test_no_timeout_override_leaves_client_default_in_effect(proxy_mod):
    """Routes that don't pass `timeout=` must NOT forward an explicit `timeout`
    kwarg to httpx at all -- httpx.request(timeout=None) means "no timeout
    whatsoever," not "use the client's own default." Confirm the kwarg is
    simply absent so the shared http_client's configured 30s default applies."""
    fake_client = _FakeHTTPClient(_json_fake_response())
    proxy_mod.http_client = fake_client

    asyncio.run(
        proxy_mod.proxy_request(
            "http://plugin-registry:8001", "v1/plugins", _FakeRequest()
        )
    )

    assert "timeout" not in fake_client.captured_kwargs


def test_long_operation_timeout_override_is_forwarded(proxy_mod):
    """A route that opts into the long-operation timeout (model pulls, RAG
    ingestion, TTS/STT, graph-rag construction) must have it actually reach
    httpx as an explicit override of the shared client's 30s default."""
    fake_client = _FakeHTTPClient(_json_fake_response())
    proxy_mod.http_client = fake_client

    asyncio.run(
        proxy_mod.proxy_request(
            "http://model-management:8005",
            "models",
            _FakeRequest("POST", body=b'{"model_id":"llama3"}'),
            timeout=proxy_mod._LONG_OPERATION_TIMEOUT,
        )
    )

    assert fake_client.captured_kwargs["timeout"] is proxy_mod._LONG_OPERATION_TIMEOUT


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


# --- _require_jwt_for_writes -------------------------------------------------
# Applied uniformly to every proxied service (#47) -- gates every mutating
# method behind a valid JWT. Had zero direct tests despite being the one
# auth check every proxy route shares.


class _FakeAuthRequest:
    def __init__(self, method, headers=None):
        self.method = method
        self.headers = headers or {}
        self.state = SimpleNamespace()


def test_get_requests_skip_the_check_entirely(proxy_mod):
    # No Authorization header at all -- would 401 if this were checked.
    proxy_mod._require_jwt_for_writes(_FakeAuthRequest("GET"))


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_mutating_methods_require_a_bearer_token(proxy_mod, method):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        proxy_mod._require_jwt_for_writes(_FakeAuthRequest(method))
    assert exc_info.value.status_code == 401


def test_non_bearer_authorization_is_rejected(proxy_mod):
    from fastapi import HTTPException

    request = _FakeAuthRequest("POST", headers={"Authorization": "Basic xxx"})
    with pytest.raises(HTTPException) as exc_info:
        proxy_mod._require_jwt_for_writes(request)
    assert exc_info.value.status_code == 401


def test_valid_bearer_token_sets_request_state_user(proxy_mod, monkeypatch):
    claims = {"sub": "user-1", "role": "admin"}
    monkeypatch.setattr(proxy_mod, "verify_jwt_token", lambda token: claims)
    request = _FakeAuthRequest("POST", headers={"Authorization": "Bearer good-token"})

    proxy_mod._require_jwt_for_writes(request)

    assert request.state.user == claims


def test_an_invalid_tokens_401_propagates(proxy_mod, monkeypatch):
    from fastapi import HTTPException

    def _boom(token):
        raise HTTPException(status_code=401, detail="Invalid token")

    monkeypatch.setattr(proxy_mod, "verify_jwt_token", _boom)
    request = _FakeAuthRequest("POST", headers={"Authorization": "Bearer bad-token"})

    with pytest.raises(HTTPException) as exc_info:
        proxy_mod._require_jwt_for_writes(request)
    assert exc_info.value.status_code == 401
