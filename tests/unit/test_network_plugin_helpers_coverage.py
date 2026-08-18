"""Unit tests filling network plugin helpers.py's remaining coverage gaps (93%).

test_network_plugin.py already covers every helper's main path -- these are
the small defensive/edge-case branches (blank lines, malformed entries,
exact-cap boundaries) that its own fixtures never happened to trigger.
"""

from plugins.network import (
    _configured_cidrs,
    _expand_targets,
    _extract_neighbor_ips,
    _parse_arp,
    _parse_snmpwalk,
    _summarize,
    _telegraf_config,
)

# ── _expand_targets: exact-cap boundaries ─────────────────────────────────────


def test_expand_targets_stops_at_cap_on_a_hostname_entry():
    assert _expand_targets("host1,host2,host3", 1) == ["host1"]


def test_expand_targets_stops_at_cap_after_a_single_address_cidr():
    # A /32 takes the net.num_addresses == 1 branch (a single append, no
    # per-ip loop) -- the cap check right after that branch is what's hit here,
    # not the for-loop's own inner cap check.
    assert _expand_targets("10.0.0.1/32,10.0.0.2/32", 1) == ["10.0.0.1"]


# ── _parse_snmpwalk: blank-line tolerance ─────────────────────────────────────


def test_parse_snmpwalk_skips_blank_lines():
    out = ".1.3.6.1.2.1.2.2.1.2.1 lo\n\n.1.3.6.1.2.1.2.2.1.2.2 eth0\n"
    assert _parse_snmpwalk(out, "1.3.6.1.2.1.2.2.1.2") == {"1": "lo", "2": "eth0"}


# ── _parse_arp: malformed OID index ───────────────────────────────────────────


def test_parse_arp_skips_indices_with_too_few_parts():
    raw = {
        "2.10.0.0.9": "0:aa:bb:cc:dd:ee",  # well-formed: ifIndex.a.b.c.d
        "1.2.3": "0:11:22:33:44:55",  # malformed: fewer than 5 dot-parts
    }
    assert _parse_arp(raw) == {"10.0.0.9": "0:aa:bb:cc:dd:ee"}


# ── _telegraf_config: non-tcp ports are skipped ───────────────────────────────


def test_telegraf_config_skips_non_tcp_ports():
    hosts = [
        {
            "host": "10.0.0.5",
            "ports": [
                {"port": 53, "protocol": "udp"},
                {"port": 22, "protocol": "tcp"},
            ],
        }
    ]
    cfg = _telegraf_config(hosts, "public")
    assert cfg.count("[[inputs.net_response]]") == 1
    assert 'address = "10.0.0.5:22"' in cfg
    assert "10.0.0.5:53" not in cfg


# ── _summarize: hosts without an ip are skipped ───────────────────────────────


def test_summarize_skips_hosts_with_no_ip():
    hosts = [
        {"host": "", "ports": [{"port": 22}]},
        {"host": "10.0.0.5", "ports": [{"port": 22}], "snmp": {"system": {}}},
    ]
    summary = _summarize(hosts)
    assert list(summary.keys()) == ["10.0.0.5"]
    assert summary["10.0.0.5"] == {"ports": [22], "snmp": True}


# ── _configured_cidrs: blank entries are skipped ──────────────────────────────


def test_configured_cidrs_skips_blank_entries():
    assert _configured_cidrs("10.0.0.0/24,,192.168.0.0/16") == [
        "10.0.0.0/24",
        "192.168.0.0/16",
    ]


# ── _extract_neighbor_ips: malformed CIDR/IP entries are tolerated ───────────


def test_extract_neighbor_ips_skips_an_invalid_cidr_in_the_allowlist():
    hosts = [{"snmp": {"arp": {"10.0.0.5": "m1"}}}]
    assert _extract_neighbor_ips(hosts, ["not-a-cidr", "10.0.0.0/29"]) == ["10.0.0.5"]


def test_extract_neighbor_ips_skips_a_malformed_arp_ip():
    hosts = [{"snmp": {"arp": {"not-an-ip": "m1", "10.0.0.5": "m2"}}}]
    assert _extract_neighbor_ips(hosts, ["10.0.0.0/29"]) == ["10.0.0.5"]
