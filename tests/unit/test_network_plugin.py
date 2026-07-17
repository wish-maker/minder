"""Unit tests for the network discovery plugin (src/plugins/network).

Pure-logic coverage (target expansion, nmap-XML parsing, telegraf-config rendering)
plus orchestration with mocked subprocess/backends so no real nmap/snmp/network runs.
"""

import asyncio

import plugins.network as netmod
from plugins.network import (
    NetworkPlugin,
    _expand_targets,
    _parse_nmap_xml,
    _parse_snmpwalk,
    _telegraf_config,
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
      <port protocol="tcp" portid="161"><state state="open"/>
        <service name="snmp"/></port>
      <port protocol="tcp" portid="8080"><state state="closed"/>
        <service name="http"/></port>
    </ports>
  </host>
  <host>
    <status state="down"/>
    <address addr="10.0.0.6" addrtype="ipv4"/>
  </host>
</nmaprun>"""


# ── pure helpers ──────────────────────────────────────────────────────────────
def test_expand_cidr_and_cap():
    assert _expand_targets("10.0.0.0/30", 256) == ["10.0.0.1", "10.0.0.2"]
    assert len(_expand_targets("10.0.0.0/24", 5)) == 5
    assert _expand_targets("example.com", 256) == ["example.com"]
    assert _expand_targets(" , ,", 256) == []


def test_parse_nmap_xml_open_ports_only():
    hosts = _parse_nmap_xml(_NMAP_XML)
    assert len(hosts) == 2
    h = hosts[0]
    assert h["host"] == "10.0.0.5"
    assert h["hostname"] == "router.local"
    assert h["state"] == "up"
    assert [p["port"] for p in h["ports"]] == [22, 161]  # closed 8080 excluded
    assert h["ports"][0]["service"] == "ssh"
    assert h["ports"][0]["product"] == "OpenSSH"
    assert hosts[1]["state"] == "down" and hosts[1]["ports"] == []


def test_parse_nmap_xml_bad_input():
    assert _parse_nmap_xml("not xml at all") == []


def test_telegraf_config_net_response_and_snmp():
    hosts = [
        {
            "host": "10.0.0.5",
            "ports": [
                {"port": 22, "protocol": "tcp"},
                {"port": 161, "protocol": "tcp"},
            ],
            "snmp": {"sysName": "router"},
        }
    ]
    cfg = _telegraf_config(hosts, "public")
    assert cfg.count("[[inputs.net_response]]") == 2
    assert 'address = "10.0.0.5:22"' in cfg
    assert "[[inputs.snmp]]" in cfg
    assert 'agents = ["udp://10.0.0.5:161"]' in cfg
    assert 'community = "public"' in cfg
    assert 'oid = "1.3.6.1.2.1.1.5.0"' in cfg  # sysName field


def test_telegraf_config_empty():
    assert _telegraf_config([], "public") == ""


# ── lifecycle + orchestration (mocked backends) ──────────────────────────────
def test_register_and_health(monkeypatch):
    monkeypatch.setenv("NETWORK_SCAN_TARGETS", "1.1.1.1")
    pl = NetworkPlugin({})
    md = asyncio.run(pl.register())
    assert md.name == "network" and md.version == "2.1.0"
    h = asyncio.run(pl.health_check())
    assert h["healthy"] is True and h["targets_configured"] is True
    assert "nmap" in h and "snmp" in h


def test_scan_via_nmap_path(monkeypatch):
    monkeypatch.setenv("NETWORK_SCAN_TARGETS", "10.0.0.5")
    monkeypatch.setattr(
        netmod.shutil, "which", lambda b: f"/usr/bin/{b}" if b == "nmap" else None
    )
    pl = NetworkPlugin({})

    async def fake_nmap(hosts):
        return _parse_nmap_xml(_NMAP_XML)

    monkeypatch.setattr(pl, "_nmap_scan", fake_nmap)
    result = asyncio.run(pl.scan())
    assert result["method"] == "nmap" and result["scanned"] == 2
    analysis = asyncio.run(pl.analyze())
    assert "10.0.0.5" in analysis["live_hosts"]
    assert analysis["open_ports"]["10.0.0.5"] == [22, 161]


def test_scan_tcp_fallback_when_no_nmap(monkeypatch):
    monkeypatch.setenv("NETWORK_SCAN_TARGETS", "10.0.0.5")
    monkeypatch.setattr(netmod.shutil, "which", lambda b: None)  # no nmap, no snmp
    pl = NetworkPlugin({})

    async def fake_fallback(hosts):
        return [
            {
                "host": "10.0.0.5",
                "hostname": "",
                "state": "up",
                "ports": [
                    {
                        "port": 80,
                        "protocol": "tcp",
                        "service": "",
                        "product": "",
                        "version": "",
                    }
                ],
            }
        ]

    monkeypatch.setattr(pl, "_tcp_fallback", fake_fallback)
    result = asyncio.run(pl.scan())
    assert result["method"] == "tcp-fallback" and result["scanned"] == 1


def test_parse_snmpwalk():
    out = ".1.3.6.1.2.1.2.2.1.2.1 lo\n.1.3.6.1.2.1.2.2.1.2.2 eth0\n"
    assert _parse_snmpwalk(out, "1.3.6.1.2.1.2.2.1.2") == {"1": "lo", "2": "eth0"}


def test_snmp_lookup_system_and_interfaces(monkeypatch):
    pl = NetworkPlugin({})

    async def fake_run(*cmd, timeout=60.0):
        tool, oid = cmd[0], cmd[-1]
        if tool == "snmpget":
            m = {
                "1.3.6.1.2.1.1.1.0": "Linux router 5.10",  # sysDescr
                "1.3.6.1.2.1.1.5.0": "router-01",  # sysName
            }
            return (0, m[oid] + "\n") if oid in m else (1, "")
        if tool == "snmpwalk" and oid == "1.3.6.1.2.1.2.2.1.2":  # ifDescr
            return 0, ".1.3.6.1.2.1.2.2.1.2.1 lo\n.1.3.6.1.2.1.2.2.1.2.2 eth0\n"
        if tool == "snmpwalk" and oid == "1.3.6.1.2.1.2.2.1.8":  # ifOperStatus
            return 0, ".1.3.6.1.2.1.2.2.1.8.1 1\n.1.3.6.1.2.1.2.2.1.8.2 1\n"
        return 1, ""

    monkeypatch.setattr(pl, "_run", fake_run)
    snmp = asyncio.run(pl._snmp_lookup("10.0.0.5"))
    assert snmp["system"]["sysDescr"] == "Linux router 5.10"
    assert snmp["system"]["sysName"] == "router-01"
    assert "sysContact" not in snmp["system"]  # unreachable → skipped
    assert [i["descr"] for i in snmp["interfaces"]] == ["lo", "eth0"]
    assert snmp["interfaces"][1]["oper_status"] == "up"


def test_snmp_lookup_skips_non_snmp_host(monkeypatch):
    pl = NetworkPlugin({})

    async def fake_run(*cmd, timeout=60.0):
        return 1, ""  # nothing responds → fast skip

    monkeypatch.setattr(pl, "_run", fake_run)
    assert asyncio.run(pl._snmp_lookup("10.0.0.9")) == {}


def test_empty_targets_scans_nothing(monkeypatch):
    monkeypatch.setenv("NETWORK_SCAN_TARGETS", "")
    pl = NetworkPlugin({})
    result = asyncio.run(pl.collect_data())
    assert result["scanned"] == 0 and result["method"] == "none"
