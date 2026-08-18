"""Unit tests filling network plugin's sink coverage gaps (src/plugins/network,
76% coverage after test_network_plugin_lifecycle_coverage.py -- this file's
follow-up, covering the four fan-out sinks: _sink_telegraf/_sink_postgres/
_sink_neo4j/_sink_rabbitmq (~180 lines, previously almost entirely untested).

test_network_plugin.py's test_reconcile_fans_out_to_all_enabled_sinks mocks
every sink out entirely (never exercising a sink's own body), and
test_sink_postgres_connect_failure_omits_raw_message covers exactly one
branch of one sink. This adds the rest: each sink's success path, its
"nothing to do" short-circuit, its HTTP/DB-error branch, and -- per the
module's own documented security contract ("sink error logs record the
exception TYPE only, never the message, to avoid leaking secrets") -- that
no sink's error response ever contains the raw exception message.

httpx.AsyncClient is monkeypatched to build a REAL client over an
httpx.MockTransport per test (matches test_registry_bundles_orchestration.py's
_ContainerOps convention) so _sink_neo4j/_sink_rabbitmq exercise real
request/response plumbing without a live server. asyncpg.connect is
monkeypatched directly (matches the existing postgres-connect-failure test's
own convention).
"""

import sys
from types import ModuleType
from unittest.mock import AsyncMock

import httpx
import pytest

from plugins.network import NetworkPlugin, _telegraf_config

_LIVE_HOST = {
    "host": "10.0.0.5",
    "hostname": "router",
    "state": "up",
    "ports": [{"port": 22, "protocol": "tcp"}],
    "snmp": {"system": {"sysDescr": "Linux router"}, "interfaces": []},
}


_RealAsyncClient = httpx.AsyncClient


def _mock_client(handler):
    return lambda **kwargs: _RealAsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://fake"
    )


# ── _sink_telegraf ────────────────────────────────────────────────────────────


def _fake_core_state(plugin_instances):
    mod = ModuleType("core.state")
    mod.plugin_instances = plugin_instances
    return mod


@pytest.mark.asyncio
async def test_sink_telegraf_unavailable_when_core_state_cannot_be_imported(
    monkeypatch,
):
    monkeypatch.setitem(sys.modules, "core.state", None)
    pl = NetworkPlugin({})

    result = await pl._sink_telegraf([_LIVE_HOST])

    assert result == {"status": "unavailable"}


@pytest.mark.asyncio
async def test_sink_telegraf_reports_not_loaded_when_telegraf_plugin_absent(
    monkeypatch,
):
    monkeypatch.setitem(sys.modules, "core.state", _fake_core_state({}))
    pl = NetworkPlugin({})

    result = await pl._sink_telegraf([_LIVE_HOST])

    assert result == {"status": "telegraf-not-loaded"}


@pytest.mark.asyncio
async def test_sink_telegraf_unchanged_when_config_is_identical(monkeypatch):
    tg = AsyncMock()
    monkeypatch.setitem(sys.modules, "core.state", _fake_core_state({"telegraf": tg}))
    pl = NetworkPlugin({})
    pl._applied_cfg = _telegraf_config([_LIVE_HOST], pl.snmp_community)

    result = await pl._sink_telegraf([_LIVE_HOST])

    assert result == {"status": "unchanged"}
    tg.set_managed_region.assert_not_called()


@pytest.mark.asyncio
async def test_sink_telegraf_applies_and_records_the_new_config(monkeypatch):
    tg = AsyncMock()
    monkeypatch.setitem(sys.modules, "core.state", _fake_core_state({"telegraf": tg}))
    pl = NetworkPlugin({})

    result = await pl._sink_telegraf([_LIVE_HOST])

    expected_cfg = _telegraf_config([_LIVE_HOST], pl.snmp_community)
    assert result == {"status": "applied", "bytes": len(expected_cfg)}
    assert pl._applied_cfg == expected_cfg
    tg.set_managed_region.assert_awaited_once_with(expected_cfg, reload=True)


@pytest.mark.asyncio
async def test_sink_telegraf_error_omits_raw_message(monkeypatch):
    tg = AsyncMock()
    tg.set_managed_region.side_effect = RuntimeError("secret config path leaked here")
    monkeypatch.setitem(sys.modules, "core.state", _fake_core_state({"telegraf": tg}))
    pl = NetworkPlugin({})

    result = await pl._sink_telegraf([_LIVE_HOST])

    assert result == {"status": "error", "error": "RuntimeError"}
    assert "secret config path" not in str(result)


# ── _sink_postgres ─────────────────────────────────────────────────────────────


class _FakePgConnection:
    def __init__(self, execute_results=None, execute_error=None):
        self.executed = []
        self.closed = False
        self._execute_results = execute_results or {}
        self._execute_error = execute_error

    async def execute(self, query, *args):
        if self._execute_error:
            raise self._execute_error
        self.executed.append((query, args))
        for marker, result in self._execute_results.items():
            if marker in query:
                return result
        return ""

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_sink_postgres_success_reports_upserted_marked_down_and_purged(
    monkeypatch,
):
    import asyncpg

    conn = _FakePgConnection(
        execute_results={
            "UPDATE network_inventory": "UPDATE 3",
            "DELETE FROM network_inventory": "DELETE 2",
        }
    )
    monkeypatch.setattr(asyncpg, "connect", AsyncMock(return_value=conn))
    pl = NetworkPlugin({})

    result = await pl._sink_postgres(
        [_LIVE_HOST], {"new": ["10.0.0.5"], "down": [], "changed": []}
    )

    assert result == {
        "status": "ok",
        "upserted": 1,
        "marked_down": 3,
        "purged": 2,
    }
    assert conn.closed is True


@pytest.mark.asyncio
async def test_sink_postgres_closes_connection_even_when_execute_fails(monkeypatch):
    import asyncpg

    conn = _FakePgConnection(execute_error=RuntimeError("disk full, password=hunter2"))
    monkeypatch.setattr(asyncpg, "connect", AsyncMock(return_value=conn))
    pl = NetworkPlugin({})

    result = await pl._sink_postgres([_LIVE_HOST], {})

    assert result == {"status": "error", "error": "RuntimeError"}
    assert "hunter2" not in str(result)
    assert conn.closed is True


# ── _sink_neo4j ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sink_neo4j_no_auth_when_neo4j_auth_env_is_malformed(monkeypatch):
    monkeypatch.delenv("NEO4J_AUTH", raising=False)
    pl = NetworkPlugin({})

    result = await pl._sink_neo4j([_LIVE_HOST])

    assert result == {"status": "no-auth"}


@pytest.mark.asyncio
async def test_sink_neo4j_success_with_no_cypher_errors(monkeypatch):
    monkeypatch.setenv("NEO4J_AUTH", "neo4j/test")

    def handler(request):
        return httpx.Response(200, json={"errors": []})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))
    pl = NetworkPlugin({})

    result = await pl._sink_neo4j([_LIVE_HOST])

    assert result == {"status": "ok", "hosts": 1, "errors": []}


@pytest.mark.asyncio
async def test_sink_neo4j_reports_cypher_errors(monkeypatch):
    monkeypatch.setenv("NEO4J_AUTH", "neo4j/test")

    def handler(request):
        return httpx.Response(
            200, json={"errors": [{"message": "constraint violated"}]}
        )

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))
    pl = NetworkPlugin({})

    result = await pl._sink_neo4j([_LIVE_HOST])

    assert result["status"] == "error"
    assert result["errors"] == [{"message": "constraint violated"}]


@pytest.mark.asyncio
async def test_sink_neo4j_non_200_http_status(monkeypatch):
    monkeypatch.setenv("NEO4J_AUTH", "neo4j/test")

    def handler(request):
        return httpx.Response(500, text="internal error")

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))
    pl = NetworkPlugin({})

    result = await pl._sink_neo4j([_LIVE_HOST])

    assert result == {"status": "error", "http_status": 500, "hosts": 1}


@pytest.mark.asyncio
async def test_sink_neo4j_non_json_response(monkeypatch):
    monkeypatch.setenv("NEO4J_AUTH", "neo4j/test")

    def handler(request):
        return httpx.Response(200, text="not json at all")

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))
    pl = NetworkPlugin({})

    result = await pl._sink_neo4j([_LIVE_HOST])

    assert result == {"status": "error", "error": "non-JSON response", "hosts": 1}


@pytest.mark.asyncio
async def test_sink_neo4j_transport_error_omits_raw_message(monkeypatch):
    monkeypatch.setenv("NEO4J_AUTH", "neo4j/test")

    def handler(request):
        raise httpx.ConnectError("neo4j:7474 unreachable, auth=secret", request=request)

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))
    pl = NetworkPlugin({})

    result = await pl._sink_neo4j([_LIVE_HOST])

    assert result == {"status": "error", "error": "ConnectError"}
    assert "secret" not in str(result)


# ── _sink_rabbitmq ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sink_rabbitmq_no_events_short_circuits():
    pl = NetworkPlugin({})

    result = await pl._sink_rabbitmq({"new": [], "down": [], "changed": []})

    assert result == {"status": "no-events"}


@pytest.mark.asyncio
async def test_sink_rabbitmq_success_counts_sent_and_routed(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"routed": True})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))
    pl = NetworkPlugin({})

    result = await pl._sink_rabbitmq({"new": ["10.0.0.5"], "down": [], "changed": []})

    assert result == {
        "status": "ok",
        "events": 1,
        "sent": 1,
        "routed": 1,
        "errors": 0,
    }


@pytest.mark.asyncio
async def test_sink_rabbitmq_partial_status_on_http_failures(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={"routed": True})
        return httpx.Response(500, text="exchange not found")

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))
    pl = NetworkPlugin({})

    result = await pl._sink_rabbitmq(
        {"new": ["10.0.0.5"], "down": ["10.0.0.6"], "changed": []}
    )

    assert result["status"] == "partial"
    assert result["events"] == 2
    assert result["sent"] == 1
    assert result["errors"] == 1


@pytest.mark.asyncio
async def test_sink_rabbitmq_tolerates_non_json_response(monkeypatch):
    def handler(request):
        return httpx.Response(200, text="not json")

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))
    pl = NetworkPlugin({})

    result = await pl._sink_rabbitmq({"new": ["10.0.0.5"], "down": [], "changed": []})

    assert result["status"] == "ok"
    assert result["sent"] == 1
    assert result["routed"] == 0  # non-JSON body -> "routed" can't be confirmed


@pytest.mark.asyncio
async def test_sink_rabbitmq_transport_error_omits_raw_message(monkeypatch):
    def handler(request):
        raise httpx.ConnectError(
            "rabbitmq:15672 auth=hunter2 unreachable", request=request
        )

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))
    pl = NetworkPlugin({})

    result = await pl._sink_rabbitmq({"new": ["10.0.0.5"], "down": [], "changed": []})

    assert result == {"status": "error", "error": "ConnectError"}
    assert "hunter2" not in str(result)
