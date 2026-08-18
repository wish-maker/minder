"""Unit tests filling telegraf plugin's remaining coverage gaps (68%).

test_telegraf_plugin.py covers the pure managed-region/TOML-validation logic with
reload=False (never touching the docker socket). Left uncovered: initialize/
collect_data/analyze/shutdown's own lines, _markers_present's OSError branch,
_split_on_markers's markers-out-of-order branch, set_managed_region's reload=True
branch, and the entire docker-engine-API surface (reload(force_restart=True),
_docker_client, _container_running, _restart_container) -- 0% before this file.

Same httpx.MockTransport pattern as test_registry_bundles_orchestration.py's
_ContainerOps tests: monkeypatch the plugin's own _docker_client to hand back an
AsyncClient wired to a fake transport, so no real docker socket is ever touched.
"""

import asyncio

import httpx
import pytest

from plugins.telegraf import TelegrafPlugin

_MARKERS = (
    "# >>> minder telegraf-plugin managed >>>\n"
    "# <<< minder telegraf-plugin managed <<<\n"
)
_BASE = '[agent]\n  interval = "10s"\n\n' + _MARKERS


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    p = tmp_path / "telegraf.conf"
    p.write_text(_BASE, encoding="utf-8")
    monkeypatch.setenv("TELEGRAF_CONFIG_PATH", str(p))
    return p


def _mock_client(handler):
    return lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://docker"
    )


# ── lifecycle: initialize/analyze/shutdown/collect_data ───────────────────────


def test_initialize_sets_status_ready(cfg):
    pl = TelegrafPlugin({})
    assert pl.status == "registered"
    asyncio.run(pl.initialize())
    assert pl.status == "ready"


def test_shutdown_sets_status(cfg):
    pl = TelegrafPlugin({})
    asyncio.run(pl.shutdown())
    assert pl.status == "shutdown"


def test_analyze_reports_managed_input_count(cfg):
    pl = TelegrafPlugin({})
    asyncio.run(
        pl.set_managed_region("[[inputs.cpu]]\n\n[[inputs.mem]]\n", reload=False)
    )

    result = asyncio.run(pl.analyze())

    assert result["managed_input_count"] == 2
    assert result["managed_inputs"] == ["cpu", "mem"]


def test_collect_data_reports_full_state(cfg, monkeypatch):
    pl = TelegrafPlugin({})
    monkeypatch.setattr(pl, "_container_running", _async(lambda: True))

    result = asyncio.run(pl.collect_data())

    assert result["config_readable"] is True
    assert result["markers_present"] is True
    assert result["managed_inputs"] == []
    assert result["telegraf_running"] is True
    assert "timestamp" in result


def _async(fn):
    async def _inner(*a, **k):
        return fn()

    return _inner


# ── _markers_present: OSError branch ──────────────────────────────────────────


def test_markers_present_false_when_config_file_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAF_CONFIG_PATH", str(tmp_path / "nonexistent.conf"))
    pl = TelegrafPlugin({})
    assert pl._markers_present() is False


# ── _split_on_markers: markers-out-of-order branch ────────────────────────────


def test_split_on_markers_rejects_reversed_markers(tmp_path, monkeypatch):
    from plugins.telegraf import _MARKER_END, _MARKER_START

    p = tmp_path / "telegraf.conf"
    p.write_text(_MARKER_END + "\n" + _MARKER_START + "\n", encoding="utf-8")
    monkeypatch.setenv("TELEGRAF_CONFIG_PATH", str(p))
    pl = TelegrafPlugin({})

    with pytest.raises(RuntimeError, match="out of order"):
        pl._split_on_markers(pl._read())


# ── set_managed_region: reload=True branch ────────────────────────────────────


def test_set_managed_region_reload_true_invokes_reload(cfg, monkeypatch):
    pl = TelegrafPlugin({})
    monkeypatch.setattr(pl, "reload", _async(lambda: {"method": "watch-config"}))

    result = asyncio.run(pl.set_managed_region("[[inputs.cpu]]", reload=True))

    assert result["reload"] == {"method": "watch-config"}


# ── reload: watch-config vs restart-fallback ──────────────────────────────────


def test_reload_default_is_watch_config_and_never_restarts(cfg, monkeypatch):
    pl = TelegrafPlugin({})
    monkeypatch.setattr(
        pl,
        "_restart_container",
        _async(lambda: pytest.fail("must not restart on the happy path")),
    )

    result = asyncio.run(pl.reload())

    assert result == {"method": "watch-config", "restarted": False}


def test_reload_force_restart_delegates_to_restart_container(cfg, monkeypatch):
    pl = TelegrafPlugin({})
    monkeypatch.setattr(pl, "_restart_container", _async(lambda: True))

    result = asyncio.run(pl.reload(force_restart=True))

    assert result == {"method": "restart", "restarted": True}


# ── _docker_client: proxy vs unix-socket fallback ─────────────────────────────


def test_docker_client_uses_tcp_proxy_when_docker_host_set(cfg, monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "tcp://docker-socket-proxy:2375")
    pl = TelegrafPlugin({})

    client = pl._docker_client()
    try:
        assert str(client.base_url) == "http://docker-socket-proxy:2375"
    finally:
        asyncio.run(client.aclose())


def test_docker_client_falls_back_to_unix_socket_when_unset(cfg, monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    pl = TelegrafPlugin({})

    client = pl._docker_client()
    try:
        assert str(client.base_url) == "http://docker"
    finally:
        asyncio.run(client.aclose())


# ── _container_running: status-code + exception branches ─────────────────────


def test_container_running_true_when_docker_reports_running(cfg, monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"State": {"Running": True}})

    pl = TelegrafPlugin({})
    monkeypatch.setattr(pl, "_docker_client", _mock_client(handler))

    assert asyncio.run(pl._container_running()) is True


def test_container_running_false_when_docker_reports_stopped(cfg, monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"State": {"Running": False}})

    pl = TelegrafPlugin({})
    monkeypatch.setattr(pl, "_docker_client", _mock_client(handler))

    assert asyncio.run(pl._container_running()) is False


def test_container_running_none_on_non_200(cfg, monkeypatch):
    def handler(request):
        return httpx.Response(404, json={"message": "no such container"})

    pl = TelegrafPlugin({})
    monkeypatch.setattr(pl, "_docker_client", _mock_client(handler))

    assert asyncio.run(pl._container_running()) is None


def test_container_running_none_on_transport_error(cfg, monkeypatch):
    def handler(request):
        raise httpx.ConnectError("socket missing", request=request)

    pl = TelegrafPlugin({})
    monkeypatch.setattr(pl, "_docker_client", _mock_client(handler))

    assert asyncio.run(pl._container_running()) is None


# ── _restart_container: status-code + exception branches ─────────────────────


def test_restart_container_true_on_204(cfg, monkeypatch):
    def handler(request):
        return httpx.Response(204)

    pl = TelegrafPlugin({})
    monkeypatch.setattr(pl, "_docker_client", _mock_client(handler))

    assert asyncio.run(pl._restart_container()) is True


def test_restart_container_false_on_non_204(cfg, monkeypatch):
    def handler(request):
        return httpx.Response(500, json={"message": "internal error"})

    pl = TelegrafPlugin({})
    monkeypatch.setattr(pl, "_docker_client", _mock_client(handler))

    assert asyncio.run(pl._restart_container()) is False


def test_restart_container_false_on_transport_error(cfg, monkeypatch):
    def handler(request):
        raise httpx.ConnectError("socket missing", request=request)

    pl = TelegrafPlugin({})
    monkeypatch.setattr(pl, "_docker_client", _mock_client(handler))

    assert asyncio.run(pl._restart_container()) is False
