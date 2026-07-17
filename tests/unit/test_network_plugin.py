"""Unit tests for the network discovery plugin (src/plugins/network).

Pure-logic coverage (target expansion, telegraf-config rendering) plus scan/analyze
with a monkeypatched probe so no real network I/O happens.
"""

import asyncio

from plugins.network import NetworkPlugin, _expand_targets, _telegraf_config


def test_expand_bare_ip():
    assert _expand_targets("1.2.3.4", 256) == ["1.2.3.4"]


def test_expand_cidr_excludes_network_and_broadcast():
    assert _expand_targets("10.0.0.0/30", 256) == ["10.0.0.1", "10.0.0.2"]


def test_expand_hostname_passthrough():
    assert _expand_targets("example.com", 256) == ["example.com"]


def test_expand_respects_max_hosts_cap():
    assert len(_expand_targets("10.0.0.0/24", 5)) == 5


def test_expand_empty_and_blank():
    assert _expand_targets("", 256) == []
    assert _expand_targets(" , ,", 256) == []


def test_telegraf_config_renders_blocks():
    cfg = _telegraf_config(["1.1.1.1", "8.8.8.8"], 53)
    assert cfg.count("[[inputs.net_response]]") == 2
    assert 'address = "1.1.1.1:53"' in cfg
    assert 'address = "8.8.8.8:53"' in cfg


def test_telegraf_config_empty_for_no_hosts():
    assert _telegraf_config([], 80) == ""


def test_register_and_health(monkeypatch):
    monkeypatch.setenv("NETWORK_SCAN_TARGETS", "1.1.1.1")
    pl = NetworkPlugin({})
    md = asyncio.run(pl.register())
    assert md.name == "network"
    h = asyncio.run(pl.health_check())
    assert h["healthy"] is True
    assert h["targets_configured"] is True


def test_scan_and_analyze_with_fake_probe(monkeypatch):
    monkeypatch.setenv("NETWORK_SCAN_TARGETS", "10.0.0.1,10.0.0.2")
    monkeypatch.setenv("NETWORK_SCAN_PORT", "80")
    pl = NetworkPlugin({})

    async def fake_probe(host, port):
        return 1.5 if host == "10.0.0.1" else None

    monkeypatch.setattr(pl, "_probe", fake_probe)
    result = asyncio.run(pl.scan())
    assert result["scanned"] == 2

    analysis = asyncio.run(pl.analyze())
    assert analysis["live"] == 1
    assert analysis["live_hosts"] == ["10.0.0.1"]
    assert 'address = "10.0.0.1:80"' in analysis["telegraf_config"]


def test_empty_targets_scans_nothing(monkeypatch):
    monkeypatch.setenv("NETWORK_SCAN_TARGETS", "")
    pl = NetworkPlugin({})
    result = asyncio.run(pl.collect_data())
    assert result["scanned"] == 0
    assert asyncio.run(pl.analyze())["live"] == 0
