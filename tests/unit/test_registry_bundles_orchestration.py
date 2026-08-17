"""Unit tests filling bundles.py's remaining coverage gaps (70%).

Existing suites (test_registry_bundles_route.py, test_registry_bundles_mutate.py)
cover the read-only list endpoint's happy path + missing-compose 503, and the
mutating endpoints' orchestration/auth contract via an INJECTED container-ops
fake. Neither exercises: the real ``_docker_base_url``/``_ContainerOps`` HTTP
plumbing that runs when no fake is injected, ``_ops()``'s DOCKER_HOST-driven
construction, ``_load``'s plugin-manifest-glob merging (+ a single bad manifest
being skipped) and its "compose has no core label" 503, ``_write_state``'s
persist-failure 503, ``_load_images``'s read-failure fallback to ``{}``, and
``_apply``'s ``ops is None`` (no docker-socket-proxy reachable) branch.

Loaded by file path (`importlib.util.spec_from_file_location`), matching the
sibling suites -- bundles.py only imports stdlib + `shared.*`, no package-
qualified plugin-registry imports that need sys.path tricks.
"""

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.auth.jwt_middleware import get_current_user

_ROUTE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "plugin-registry"
    / "routes"
    / "bundles.py"
)

_COMPOSE = """\
services:
  traefik:
    labels: [minder.bundle=core]
  ollama:
    labels:
    - minder.bundle=inference,rag
"""

_COMPOSE_NO_CORE = """\
services:
  ollama:
    labels:
    - minder.bundle=inference
"""


def _load_route_module():
    spec = importlib.util.spec_from_file_location("registry_bundles_orch", _ROUTE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _settings(tmp_path, *, compose_text=_COMPOSE, plugins_path=None):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(compose_text, encoding="utf-8")
    return (
        SimpleNamespace(
            BUNDLES_COMPOSE_PATH=str(compose),
            BUNDLES_STATE_PATH=str(tmp_path / "bundles.state.json"),
            CONTAINER_PREFIX="minder",
            PLUGINS_PATH=plugins_path,
        ),
        compose,
    )


def _client(mod, settings, *, container_ops=None, role="admin"):
    logger = SimpleNamespace(info=lambda *a, **k: None)
    app = FastAPI()
    app.include_router(
        mod.build_bundles_router(
            settings=settings, logger=logger, container_ops=container_ops
        )
    )
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "tester",
        "role": role,
    }
    return TestClient(app, raise_server_exceptions=True)


# --- _docker_base_url -----------------------------------------------------------


def test_docker_base_url_converts_tcp_scheme(monkeypatch):
    mod = _load_route_module()
    monkeypatch.setenv("DOCKER_HOST", "tcp://docker-socket-proxy:2375")
    assert mod._docker_base_url() == "http://docker-socket-proxy:2375"


def test_docker_base_url_empty_when_unset(monkeypatch):
    mod = _load_route_module()
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    assert mod._docker_base_url() == ""


def test_docker_base_url_empty_for_non_tcp_scheme(monkeypatch):
    mod = _load_route_module()
    monkeypatch.setenv("DOCKER_HOST", "unix:///var/run/docker.sock")
    assert mod._docker_base_url() == ""


# --- _ContainerOps: real HTTP plumbing over a mock transport ---------------------


def _ops_with_transport(mod, handler):
    ops = mod._ContainerOps("http://fake-proxy", "minder")
    ops._client = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://fake-proxy"
    )
    return ops


def test_container_ops_cname_prefixes_with_container_prefix():
    mod = _load_route_module()
    ops = mod._ContainerOps("http://fake", "minder")
    assert ops._cname("weather") == "minder-weather"


def test_container_ops_client_builds_an_async_client_with_the_base_url():
    mod = _load_route_module()
    ops = mod._ContainerOps("http://fake-proxy", "minder", timeout=5.0)
    client = ops._client()
    try:
        assert isinstance(client, httpx.AsyncClient)
        assert str(client.base_url) == "http://fake-proxy"
        assert client.timeout.connect == 5.0
    finally:
        asyncio.run(client.aclose())


def test_container_ops_start_204_is_changed():
    mod = _load_route_module()

    def handler(request):
        assert request.url.path == "/containers/minder-weather/start"
        return httpx.Response(204)

    ops = _ops_with_transport(mod, handler)
    assert asyncio.run(ops.start("weather")) == "changed"


def test_container_ops_stop_304_is_already():
    mod = _load_route_module()
    ops = _ops_with_transport(mod, lambda r: httpx.Response(304))
    assert asyncio.run(ops.stop("weather")) == "already"


def test_container_ops_404_is_absent():
    mod = _load_route_module()
    ops = _ops_with_transport(mod, lambda r: httpx.Response(404))
    assert asyncio.run(ops.start("weather")) == "absent"


def test_container_ops_unexpected_status_is_error():
    mod = _load_route_module()
    ops = _ops_with_transport(mod, lambda r: httpx.Response(500))
    assert asyncio.run(ops.start("weather")) == "error"


def test_container_ops_transport_failure_is_error():
    mod = _load_route_module()

    def handler(request):
        raise httpx.ConnectError("proxy unreachable", request=request)

    ops = _ops_with_transport(mod, handler)
    assert asyncio.run(ops.start("weather")) == "error"


# --- _ops(): DOCKER_HOST-driven construction inside the router -------------------


def test_ops_returns_none_when_docker_host_unset_and_nothing_injected(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    mod = _load_route_module()
    settings, _ = _settings(tmp_path)
    client = _client(mod, settings, container_ops=None)

    r = client.post("/v1/bundles/inference/enable")

    assert r.status_code == 200
    body = r.json()
    # No proxy reachable -> _apply's ops-is-None branch: intent persisted, nothing
    # orchestrated, every target reported pending_create.
    assert body["pending_create"] == ["ollama"]
    assert body["started"] == []


def test_ops_builds_real_container_ops_from_docker_host(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "tcp://docker-socket-proxy:2375")
    mod = _load_route_module()
    captured = {}

    class _FakeContainerOps:
        def __init__(self, base_url, prefix):
            captured["base_url"] = base_url
            captured["prefix"] = prefix

        async def start(self, service):
            return "changed"

        async def stop(self, service):
            return "changed"

    monkeypatch.setattr(mod, "_ContainerOps", _FakeContainerOps)
    settings, _ = _settings(tmp_path)
    client = _client(mod, settings, container_ops=None)

    r = client.post("/v1/bundles/inference/enable")

    assert r.status_code == 200
    assert captured["base_url"] == "http://docker-socket-proxy:2375"
    assert captured["prefix"] == "minder"


# --- _load: core-missing 503 + plugin-manifest-glob merging ---------------------


def test_list_bundles_503_when_compose_has_no_core_label(tmp_path):
    mod = _load_route_module()
    settings, _ = _settings(tmp_path, compose_text=_COMPOSE_NO_CORE)
    client = _client(mod, settings)

    r = client.get("/v1/bundles")

    assert r.status_code == 503
    assert "no minder.bundle=" in r.json()["detail"]


def test_list_bundles_merges_claims_from_plugin_manifests(tmp_path):
    mod = _load_route_module()
    plugins_dir = tmp_path / "plugins"
    (plugins_dir / "weather").mkdir(parents=True)
    (plugins_dir / "weather" / "manifest.yml").write_text(
        "bundle: analytics\nclaims:\n  - service: telegraf\n", encoding="utf-8"
    )
    settings, _ = _settings(tmp_path, plugins_path=str(plugins_dir))
    client = _client(mod, settings)

    r = client.get("/v1/bundles")

    assert r.status_code == 200
    by_name = {b["name"]: b for b in r.json()["bundles"]}
    assert by_name["analytics"]["claims"] == ["telegraf"]


def test_list_bundles_skips_an_unreadable_manifest_without_failing(tmp_path):
    mod = _load_route_module()
    plugins_dir = tmp_path / "plugins"
    # A manifest.yml that's actually a directory -> Path.read_text() raises
    # IsADirectoryError (an OSError), which _load must swallow (`continue`),
    # not let bubble up and 500 the whole endpoint.
    (plugins_dir / "broken" / "manifest.yml").mkdir(parents=True)
    settings, _ = _settings(tmp_path, plugins_path=str(plugins_dir))
    client = _client(mod, settings)

    r = client.get("/v1/bundles")

    assert r.status_code == 200


def test_list_bundles_ignores_plugins_path_when_unset(tmp_path):
    mod = _load_route_module()
    settings, _ = _settings(tmp_path, plugins_path=None)
    client = _client(mod, settings)

    r = client.get("/v1/bundles")

    assert r.status_code == 200


# --- _write_state: persist failure -----------------------------------------------


def test_enable_bundle_503_when_state_file_cannot_be_written(tmp_path):
    mod = _load_route_module()
    settings, _ = _settings(tmp_path)
    # Point the state path at a directory -> write_text() raises IsADirectoryError.
    bad_state_dir = tmp_path / "bundles.state.json"
    bad_state_dir.mkdir()
    settings.BUNDLES_STATE_PATH = str(bad_state_dir)
    client = _client(mod, settings)

    r = client.post("/v1/bundles/inference/enable")

    assert r.status_code == 503
    assert "cannot persist bundle state" in r.json()["detail"]


# --- _load_images: read failure falls back to {} --------------------------------


def test_list_bundles_image_none_when_compose_becomes_unreadable_for_images(
    tmp_path, monkeypatch
):
    mod = _load_route_module()
    settings, compose_path = _settings(tmp_path)
    client = _client(mod, settings)

    real_path_cls = mod.Path
    call_counts = {"n": 0}

    def flaky_path(p):
        p_str = str(p)
        if p_str == str(compose_path):
            call_counts["n"] += 1
            if (
                call_counts["n"] > 1
            ):  # 1st call is _load()'s read; 2nd is _load_images()'s

                class _Boom:
                    def read_text(self, *a, **k):
                        raise OSError("compose file vanished")

                return _Boom()
        return real_path_cls(p)

    monkeypatch.setattr(mod, "Path", flaky_path)

    r = client.get("/v1/bundles")

    assert r.status_code == 200
    by_name = {b["name"]: b for b in r.json()["bundles"]}
    # _load_images() failed -> every service's image falls back to None instead
    # of the pinned tag, but the endpoint itself must not fail.
    services = by_name["inference"]["services"]
    assert all(s["image"] is None for s in services)
