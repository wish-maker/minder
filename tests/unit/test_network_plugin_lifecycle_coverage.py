"""Unit tests filling network plugin's lifecycle/scan-backend coverage gaps
(src/plugins/network, 58% coverage).

test_network_plugin.py already covers the pure helpers and orchestration with
`_nmap_scan`/`_tcp_fallback` themselves MOCKED OUT (only ever asserting on
`scan()`'s dispatch, never exercising either backend's own body). Left
entirely untested: initialize's task-creation/no-running-loop/interval=0
branches, the autonomous _loop's sink-warning/CancelledError/generic-exception
branches, shutdown's task-cancel path, _nmap_scan's own rc==0/!=0 branches,
_tcp_fallback's own open/down/writer-close-error branches, and _discover's
SNMP-enrichment-of-live-hosts branch.

The sinks (_sink_telegraf/_sink_postgres/_sink_neo4j/_sink_rabbitmq, ~180
lines) are a separate, self-contained follow-up -- each needs its own
asyncpg/httpx mocking and is large enough to deserve its own PR.
"""

import asyncio
import sys

import pytest

import plugins.network as netmod
from plugins.network import (
    _HR_PROC_LOAD_OID,
    _HR_STOR_DESCR_OID,
    _HR_STOR_SIZE_OID,
    _HR_STOR_USED_OID,
    _HR_UPTIME_OID,
    NetworkPlugin,
)

_NMAP_XML = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="10.0.0.5" addrtype="ipv4"/>
    <hostnames><hostname name="router.local"/></hostnames>
    <ports>
      <port protocol="tcp" portid="22"><state state="open"/>
        <service name="ssh" product="OpenSSH" version="9.2"/></port>
    </ports>
  </host>
  <host>
    <status state="down"/>
    <address addr="10.0.0.6" addrtype="ipv4"/>
  </host>
</nmaprun>"""


# ── initialize / _loop / shutdown ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_initialize_starts_the_reconcile_loop_task():
    pl = NetworkPlugin({})
    pl.interval = 3600

    await pl.initialize()

    assert isinstance(pl._task, asyncio.Task)
    await pl.shutdown()
    assert pl._task is None
    assert pl.status == "shutdown"


@pytest.mark.asyncio
async def test_initialize_skips_task_when_interval_is_zero():
    pl = NetworkPlugin({})
    pl.interval = 0

    await pl.initialize()

    assert pl._task is None
    assert pl.status == "ready"


@pytest.mark.asyncio
async def test_initialize_tolerates_no_running_loop(monkeypatch):
    pl = NetworkPlugin({})
    pl.interval = 3600
    monkeypatch.setattr(
        asyncio, "get_running_loop", lambda: (_ for _ in ()).throw(RuntimeError())
    )

    await pl.initialize()

    assert pl._task is None


@pytest.mark.asyncio
async def test_shutdown_is_a_noop_without_a_task():
    pl = NetworkPlugin({})

    await pl.shutdown()  # must not raise

    assert pl.status == "shutdown"


@pytest.mark.asyncio
async def test_loop_survives_reconcile_exceptions_and_keeps_running(monkeypatch):
    pl = NetworkPlugin({})
    pl.interval = 0
    calls = {"n": 0}

    async def fake_reconcile():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return {"sinks": {}}

    monkeypatch.setattr(pl, "reconcile", fake_reconcile)
    task = asyncio.create_task(pl._loop())
    for _ in range(10):
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert calls["n"] >= 2  # the raise on the first cycle didn't kill the loop


@pytest.mark.asyncio
async def test_loop_logs_a_warning_when_a_sink_reports_error_or_partial(
    monkeypatch, caplog
):
    pl = NetworkPlugin({})
    pl.interval = 0

    async def fake_reconcile():
        return {"sinks": {"postgres": {"status": "error"}, "neo4j": {"status": "ok"}}}

    monkeypatch.setattr(pl, "reconcile", fake_reconcile)
    task = asyncio.create_task(pl._loop())
    for _ in range(5):
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert any("sink issues" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_loop_propagates_cancellation_during_sleep():
    pl = NetworkPlugin({})
    pl.interval = 3600  # long enough that cancellation lands inside the sleep

    task = asyncio.create_task(pl._loop())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


# ── _nmap_scan ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_nmap_scan_parses_xml_on_success(monkeypatch):
    pl = NetworkPlugin({})

    async def fake_run(*cmd, timeout=60.0):
        return 0, _NMAP_XML

    monkeypatch.setattr(pl, "_run", fake_run)

    hosts = await pl._nmap_scan(["10.0.0.5", "10.0.0.6"])

    assert len(hosts) == 2
    assert hosts[0]["host"] == "10.0.0.5"


@pytest.mark.asyncio
async def test_nmap_scan_empty_on_nonzero_exit(monkeypatch):
    pl = NetworkPlugin({})

    async def fake_run(*cmd, timeout=60.0):
        return 1, ""

    monkeypatch.setattr(pl, "_run", fake_run)

    assert await pl._nmap_scan(["10.0.0.5"]) == []


# ── _tcp_fallback ────────────────────────────────────────────────────────────


class _FakeWriter:
    def __init__(self, wait_closed_error=None):
        self.closed = False
        self._wait_closed_error = wait_closed_error

    def close(self):
        self.closed = True

    async def wait_closed(self):
        if self._wait_closed_error:
            raise self._wait_closed_error


@pytest.mark.asyncio
async def test_tcp_fallback_reports_open_and_down_hosts(monkeypatch):
    pl = NetworkPlugin({})
    pl.ports = "8080,22"  # first port (8080) is what gets probed

    async def fake_open_connection(host, port):
        if host == "10.0.0.5":
            return object(), _FakeWriter()
        raise OSError("connection refused")

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)

    hosts = await pl._tcp_fallback(["10.0.0.5", "10.0.0.6"])

    by_host = {h["host"]: h for h in hosts}
    assert by_host["10.0.0.5"]["state"] == "up"
    assert by_host["10.0.0.5"]["ports"][0] == {
        "port": 8080,
        "protocol": "tcp",
        "service": "",
        "product": "",
        "version": "",
    }
    assert by_host["10.0.0.6"]["state"] == "down"
    assert by_host["10.0.0.6"]["ports"] == []


@pytest.mark.asyncio
async def test_tcp_fallback_tolerates_writer_close_error(monkeypatch):
    pl = NetworkPlugin({})
    pl.ports = "8080"

    async def fake_open_connection(host, port):
        return object(), _FakeWriter(wait_closed_error=OSError("already gone"))

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)

    hosts = await pl._tcp_fallback(["10.0.0.5"])  # must not raise

    assert hosts[0]["state"] == "up"


@pytest.mark.asyncio
async def test_tcp_fallback_falls_back_to_port_80_on_bad_ports_config(monkeypatch):
    pl = NetworkPlugin({})
    pl.ports = "not-a-number"
    seen_ports = []

    async def fake_open_connection(host, port):
        seen_ports.append(port)
        raise OSError("refused")

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)

    await pl._tcp_fallback(["10.0.0.5"])

    assert seen_ports == [80]


@pytest.mark.asyncio
async def test_tcp_fallback_times_out_as_down(monkeypatch):
    pl = NetworkPlugin({})
    pl.ports = "8080"

    async def hangs_forever(host, port):
        await asyncio.sleep(3600)

    monkeypatch.setattr(asyncio, "open_connection", hangs_forever)
    monkeypatch.setattr(netmod, "_CONNECT_TIMEOUT", 0.01)

    hosts = await pl._tcp_fallback(["10.0.0.5"])

    assert hosts[0]["state"] == "down"


# ── _discover: SNMP enrichment of live hosts ─────────────────────────────────


@pytest.mark.asyncio
async def test_discover_enriches_live_hosts_with_snmp_when_enabled(monkeypatch):
    monkeypatch.setenv("NETWORK_SCAN_TARGETS", "10.0.0.5,10.0.0.6")
    pl = NetworkPlugin({})
    pl.snmp_enabled = True
    monkeypatch.setattr(netmod.shutil, "which", lambda b: f"/usr/bin/{b}")

    async def fake_nmap(hosts):
        return [
            {"host": "10.0.0.5", "hostname": "", "state": "up", "ports": []},
            {"host": "10.0.0.6", "hostname": "", "state": "down", "ports": []},
        ]

    snmp_calls = []

    async def fake_snmp_lookup(host):
        snmp_calls.append(host)
        return {"system": {"sysDescr": "router"}} if host == "10.0.0.5" else {}

    monkeypatch.setattr(pl, "_nmap_scan", fake_nmap)
    monkeypatch.setattr(pl, "_snmp_lookup", fake_snmp_lookup)

    result = await pl._discover()

    # only the live host is probed -- the down one is skipped entirely
    assert snmp_calls == ["10.0.0.5"]
    by_host = {h["host"]: h for h in result["hosts"]}
    assert by_host["10.0.0.5"]["snmp"] == {"system": {"sysDescr": "router"}}
    assert "snmp" not in by_host["10.0.0.6"]


@pytest.mark.asyncio
async def test_discover_skips_snmp_when_disabled(monkeypatch):
    monkeypatch.setenv("NETWORK_SCAN_TARGETS", "10.0.0.5")
    pl = NetworkPlugin({})
    pl.snmp_enabled = False
    monkeypatch.setattr(netmod.shutil, "which", lambda b: f"/usr/bin/{b}")

    async def fake_nmap(hosts):
        return [{"host": "10.0.0.5", "hostname": "", "state": "up", "ports": []}]

    called = {"n": 0}

    async def fail_if_called(host):
        called["n"] += 1
        return {}

    monkeypatch.setattr(pl, "_nmap_scan", fake_nmap)
    monkeypatch.setattr(pl, "_snmp_lookup", fail_if_called)

    result = await pl._discover()

    assert called["n"] == 0
    assert "snmp" not in result["hosts"][0]


# ── _loop: CancelledError raised from within reconcile itself ────────────────


@pytest.mark.asyncio
async def test_loop_reraises_cancellation_raised_from_within_reconcile():
    pl = NetworkPlugin({})
    pl.interval = 0
    started = asyncio.Event()

    async def slow_reconcile():
        started.set()
        await asyncio.sleep(3600)
        return {"sinks": {}}

    pl.reconcile = slow_reconcile
    task = asyncio.create_task(pl._loop())
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


# ── _run: real subprocess execution (success/nonzero-exit/OSError) ───────────


@pytest.mark.asyncio
async def test_run_captures_stdout_on_success():
    pl = NetworkPlugin({})

    rc, out = await pl._run(sys.executable, "-c", "print('hello', end='')")

    assert rc == 0
    assert out == "hello"


@pytest.mark.asyncio
async def test_run_returns_the_process_exit_code():
    pl = NetworkPlugin({})

    rc, _ = await pl._run(sys.executable, "-c", "import sys; sys.exit(3)")

    assert rc == 3


@pytest.mark.asyncio
async def test_run_returns_1_when_the_binary_cannot_be_started(monkeypatch):
    pl = NetworkPlugin({})

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        raise OSError("no such file or directory")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    rc, out = await pl._run("definitely-not-a-real-binary")

    assert rc == 1
    assert out == ""


# ── _snmp_host_resources: uptime/processor_load/storage population ──────────


@pytest.mark.asyncio
async def test_snmp_host_resources_populates_uptime_load_and_storage(monkeypatch):
    pl = NetworkPlugin({})

    async def fake_run(*cmd, timeout=60.0):
        tool, oid = cmd[0], cmd[-1]
        if tool == "snmpget" and oid == _HR_UPTIME_OID:
            return 0, "12345\n"
        if tool == "snmpbulkwalk":
            if oid == _HR_PROC_LOAD_OID:
                return 0, ".1.3.6.1.2.1.25.3.3.1.2.1 5\n"
            if oid == _HR_STOR_DESCR_OID:
                return 0, ".1.3.6.1.2.1.25.2.3.1.3.1 /\n"
            if oid == _HR_STOR_SIZE_OID:
                return 0, ".1.3.6.1.2.1.25.2.3.1.5.1 1000\n"
            if oid == _HR_STOR_USED_OID:
                return 0, ".1.3.6.1.2.1.25.2.3.1.6.1 400\n"
        return 1, ""

    monkeypatch.setattr(pl, "_run", fake_run)

    hr = await pl._snmp_host_resources("10.0.0.5")

    assert hr["uptime"] == "12345"
    assert hr["processor_load"] == ["5"]
    assert hr["storage"] == [{"descr": "/", "size": "1000", "used": "400"}]


# ── reconcile: an expanded IP reappearing resets its miss counter ────────────


def _canned_collect(pl, hosts):
    async def fake_discover():
        pl._last = {
            "timestamp": "t",
            "targets": "x",
            "method": "nmap",
            "scanned": len(hosts),
            "hosts": hosts,
        }
        return pl._last

    return fake_discover


@pytest.mark.asyncio
async def test_reconcile_resets_miss_count_when_expanded_ip_reappears(monkeypatch):
    monkeypatch.setenv("NETWORK_SCAN_TARGETS", "10.0.0.1")
    monkeypatch.setenv("NETWORK_EXPAND_MISS_LIMIT", "2")
    for s in (
        "NETWORK_AUTO_APPLY",
        "NETWORK_SINK_POSTGRES",
        "NETWORK_SINK_NEO4J",
        "NETWORK_SINK_RABBITMQ",
    ):
        monkeypatch.setenv(s, "0")
    pl = NetworkPlugin({})
    pl._expanded = {"10.0.0.9"}
    pl._expanded_miss = {"10.0.0.9": 1}  # already missed once
    pl._prev = {
        "10.0.0.1": {"ports": [], "snmp": False},
        "10.0.0.9": {"ports": [], "snmp": False},
    }
    hosts = [
        {"host": "10.0.0.1", "state": "up", "ports": []},
        {"host": "10.0.0.9", "state": "up", "ports": []},  # reappeared -> resets miss
    ]
    monkeypatch.setattr(pl, "_discover", _canned_collect(pl, hosts))

    result = await pl.reconcile()

    assert result["expanded_evicted"] == []
    assert (
        pl._expanded_miss.get("10.0.0.9") is None
    )  # miss counter cleared, not just low
