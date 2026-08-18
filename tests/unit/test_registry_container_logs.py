"""Unit tests for plugin-registry's container-logs endpoint (Status page).

The route is loaded by path (shared `routes` package name across services in
one pytest process) exactly like the bundles route tests. Docker calls go
through a fake `httpx.AsyncClient` via monkeypatch -- no real socket-proxy.
"""

import importlib.util
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROUTE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "plugin-registry"
    / "routes"
    / "containers.py"
)


def _load_route_module():
    spec = importlib.util.spec_from_file_location("registry_containers_route", _ROUTE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _frame(stream_type: int, text: bytes) -> bytes:
    return struct.pack(">BxxxI", stream_type, len(text)) + text


def test_demux_splits_stdout_and_stderr_frames():
    mod = _load_route_module()
    raw = _frame(1, b"hello\n") + _frame(2, b"oops\n")
    frames = mod._demux_docker_log_stream(raw)
    assert frames == [
        {"stream": "stdout", "text": "hello\n"},
        {"stream": "stderr", "text": "oops\n"},
    ]


def test_demux_empty_stream():
    mod = _load_route_module()
    assert mod._demux_docker_log_stream(b"") == []


class _FakeResponse:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content


class _FakeAsyncClient:
    """Stands in for `httpx.AsyncClient` as an async context manager, always
    returning the given canned response regardless of the request."""

    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, path, params=None):
        return self._response


def _client(mod, *, response, monkeypatch, auth=True):
    monkeypatch.setattr(
        mod.httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(response)
    )
    monkeypatch.setenv("DOCKER_HOST", "tcp://docker-socket-proxy:2375")
    settings = SimpleNamespace(CONTAINER_PREFIX="minder")
    app = FastAPI()
    app.include_router(mod.build_containers_router(settings=settings))
    if auth:
        app.dependency_overrides[mod.get_current_user] = lambda: {"sub": "tester"}
    return TestClient(app, raise_server_exceptions=True)


def test_unknown_service_404(monkeypatch):
    mod = _load_route_module()
    client = _client(mod, response=_FakeResponse(200), monkeypatch=monkeypatch)
    r = client.get("/v1/containers/not-a-real-service/logs")
    assert r.status_code == 404


def test_known_service_returns_demuxed_lines(monkeypatch):
    mod = _load_route_module()
    raw = _frame(1, b"booted\n")
    client = _client(
        mod, response=_FakeResponse(200, content=raw), monkeypatch=monkeypatch
    )
    r = client.get("/v1/containers/marketplace/logs")
    assert r.status_code == 200
    assert r.json() == {
        "name": "marketplace",
        "lines": [{"stream": "stdout", "text": "booted\n"}],
    }


def test_container_not_running_404(monkeypatch):
    mod = _load_route_module()
    client = _client(mod, response=_FakeResponse(404), monkeypatch=monkeypatch)
    r = client.get("/v1/containers/marketplace/logs")
    assert r.status_code == 404


def test_requires_auth(monkeypatch):
    mod = _load_route_module()
    client = _client(
        mod, response=_FakeResponse(200), monkeypatch=monkeypatch, auth=False
    )
    r = client.get("/v1/containers/marketplace/logs")
    assert r.status_code in (401, 403)


def test_no_docker_host_returns_503(monkeypatch):
    mod = _load_route_module()
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    settings = SimpleNamespace(CONTAINER_PREFIX="minder")
    app = FastAPI()
    app.include_router(mod.build_containers_router(settings=settings))
    app.dependency_overrides[mod.get_current_user] = lambda: {"sub": "tester"}
    r = TestClient(app).get("/v1/containers/marketplace/logs")
    assert r.status_code == 503


@pytest.mark.parametrize("tail", [0, 2001])
def test_tail_out_of_range_422(monkeypatch, tail):
    mod = _load_route_module()
    client = _client(mod, response=_FakeResponse(200), monkeypatch=monkeypatch)
    r = client.get(f"/v1/containers/marketplace/logs?tail={tail}")
    assert r.status_code == 422


class _RaisingAsyncClient:
    """Stands in for httpx.AsyncClient when the request itself fails
    (socket-proxy unreachable/timeout), rather than returning a response."""

    def __init__(self, error):
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, path, params=None):
        raise self._error


def test_docker_socket_proxy_transport_error_returns_503(monkeypatch):
    mod = _load_route_module()
    monkeypatch.setattr(
        mod.httpx,
        "AsyncClient",
        lambda *a, **k: _RaisingAsyncClient(mod.httpx.ConnectError("refused")),
    )
    monkeypatch.setenv("DOCKER_HOST", "tcp://docker-socket-proxy:2375")
    settings = SimpleNamespace(CONTAINER_PREFIX="minder")
    app = FastAPI()
    app.include_router(mod.build_containers_router(settings=settings))
    app.dependency_overrides[mod.get_current_user] = lambda: {"sub": "tester"}
    r = TestClient(app, raise_server_exceptions=True).get(
        "/v1/containers/marketplace/logs"
    )
    assert r.status_code == 503


def test_unexpected_docker_socket_proxy_status_returns_502(monkeypatch):
    mod = _load_route_module()
    client = _client(mod, response=_FakeResponse(500), monkeypatch=monkeypatch)
    r = client.get("/v1/containers/marketplace/logs")
    assert r.status_code == 502
