"""Pure helpers + SNMP OID constants for the network plugin.

Everything here is side-effect-free (no subprocess, no network) and unit-tested in
isolation. ``__init__`` imports these (and re-exposes them), so both the plugin and
the tests reference them via ``plugins.network``. Names keep their ``_`` prefix to
match their long-standing use as network-plugin internals.
"""

import ipaddress
from typing import Dict, List
from xml.etree import ElementTree

# ── SNMP OID constants ────────────────────────────────────────────────────────
_SNMP_SYSTEM_OIDS = {
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "sysObjectID": "1.3.6.1.2.1.1.2.0",
    "sysUpTime": "1.3.6.1.2.1.1.3.0",
    "sysContact": "1.3.6.1.2.1.1.4.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
    "sysLocation": "1.3.6.1.2.1.1.6.0",
}
_IF_DESCR_OID = "1.3.6.1.2.1.2.2.1.2"
_IF_TYPE_OID = "1.3.6.1.2.1.2.2.1.3"
_IF_SPEED_OID = "1.3.6.1.2.1.2.2.1.5"
_IF_MAC_OID = "1.3.6.1.2.1.2.2.1.6"
_IF_OPERSTATUS_OID = "1.3.6.1.2.1.2.2.1.8"
_IF_ALIAS_OID = "1.3.6.1.2.1.31.1.1.1.18"  # ifXTable ifAlias
_IF_OPER = {"1": "up", "2": "down", "3": "testing"}

# Host Resources MIB (device health / inventory).
_HR_UPTIME_OID = "1.3.6.1.2.1.25.1.1.0"
_HR_MEMSIZE_OID = "1.3.6.1.2.1.25.2.2.0"
_HR_PROC_LOAD_OID = "1.3.6.1.2.1.25.3.3.1.2"  # per-processor load %
_HR_STOR_DESCR_OID = "1.3.6.1.2.1.25.2.3.1.3"
_HR_STOR_SIZE_OID = "1.3.6.1.2.1.25.2.3.1.5"  # in allocation units
_HR_STOR_USED_OID = "1.3.6.1.2.1.25.2.3.1.6"

# ARP / neighbour table: ipNetToMediaPhysAddress (index = ifIndex.a.b.c.d → MAC).
_ARP_MAC_OID = "1.3.6.1.2.1.4.22.1.2"


# ── discovery / parsing helpers ───────────────────────────────────────────────
def _expand_targets(spec: str, max_hosts: int) -> List[str]:
    """Expand a comma-separated hosts/CIDRs spec into individual host strings,
    capped at ``max_hosts``. A bare IP/hostname passes through; a CIDR expands."""
    hosts: List[str] = []
    for raw in spec.split(","):
        item = raw.strip()
        if not item:
            continue
        try:
            net = ipaddress.ip_network(item, strict=False)
        except ValueError:
            hosts.append(item)  # hostname (not an IP/CIDR)
            if len(hosts) >= max_hosts:
                return hosts[:max_hosts]
            continue
        if net.num_addresses == 1:
            hosts.append(str(net.network_address))
        else:
            for ip in net.hosts():
                hosts.append(str(ip))
                if len(hosts) >= max_hosts:
                    return hosts[:max_hosts]
        if len(hosts) >= max_hosts:
            return hosts[:max_hosts]
    return hosts[:max_hosts]


def _parse_nmap_xml(xml_text: str) -> List[Dict]:
    """Parse ``nmap -oX`` output into [{host, hostname, state, ports:[...]}]."""
    hosts: List[Dict] = []
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return hosts
    for host_el in root.findall("host"):
        status = host_el.find("status")
        state = status.get("state") if status is not None else "unknown"
        addr = ""
        for a in host_el.findall("address"):
            if a.get("addrtype") in ("ipv4", "ipv6"):
                addr = a.get("addr", "")
                break
        hostname = ""
        hn = host_el.find("hostnames/hostname")
        if hn is not None:
            hostname = hn.get("name", "")
        ports = []
        for p in host_el.findall("ports/port"):
            pstate = p.find("state")
            if pstate is None or pstate.get("state") != "open":
                continue
            svc = p.find("service")
            ports.append(
                {
                    "port": int(p.get("portid", "0")),
                    "protocol": p.get("protocol", "tcp"),
                    "service": svc.get("name", "") if svc is not None else "",
                    "product": svc.get("product", "") if svc is not None else "",
                    "version": svc.get("version", "") if svc is not None else "",
                }
            )
        hosts.append(
            {"host": addr, "hostname": hostname, "state": state, "ports": ports}
        )
    return hosts


def _parse_snmpwalk(text: str, base_oid: str) -> Dict[str, str]:
    """Parse ``snmpbulkwalk -Oqn`` output (numeric-OID, quiet) into {index: value},
    where index is the OID suffix after ``base_oid``."""
    result: Dict[str, str] = {}
    prefix = base_oid if base_oid.startswith(".") else "." + base_oid
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(" ", 1)
        oid = parts[0]
        value = parts[1].strip().strip('"') if len(parts) > 1 else ""
        if oid.startswith(prefix + "."):
            result[oid[len(prefix) + 1 :]] = value
    return result


def _normalize_mac(mac: str) -> str:
    """Normalise a MAC to lowercase colon-separated (net-snmp renders it space- or
    colon-separated depending on flags/agent)."""
    return mac.replace(" ", ":").strip(":").lower()


def _parse_arp(raw: Dict[str, str]) -> Dict[str, str]:
    """Turn a parsed ipNetToMediaPhysAddress walk ({index: mac}) into {ip: mac}.
    The OID index is ``<ifIndex>.<a>.<b>.<c>.<d>``; value is the MAC."""
    out: Dict[str, str] = {}
    for index, mac in raw.items():
        parts = index.split(".")
        if len(parts) < 5:
            continue
        ip = ".".join(parts[-4:])
        out[ip] = _normalize_mac(mac)
    return out


def _telegraf_config(hosts: List[Dict], snmp_community: str) -> str:
    """Render telegraf inputs for discovered hosts: net_response per open TCP port,
    and an snmp input per SNMP-capable host.

    NOTE: consumed by the telegraf plugin's set_managed_region(), which validates it
    as TOML — keep the output valid TOML (see src/plugins/telegraf)."""
    blocks: List[str] = []
    for h in hosts:
        addr = h.get("host", "")
        for p in h.get("ports", []):
            if p.get("protocol", "tcp") != "tcp":
                continue
            blocks.append(
                "[[inputs.net_response]]\n"
                '  protocol = "tcp"\n'
                f'  address = "{addr}:{p["port"]}"\n'
                '  timeout = "5s"'
            )
        if h.get("snmp"):
            fields = "\n".join(
                "  [[inputs.snmp.field]]\n"
                f'    name = "{name}"\n'
                f'    oid = "{oid}"'
                for name, oid in _SNMP_SYSTEM_OIDS.items()
            )
            blocks.append(
                "[[inputs.snmp]]\n"
                f'  agents = ["udp://{addr}:161"]\n'
                "  version = 2\n"
                f'  community = "{snmp_community}"\n' + fields
            )
    return "\n".join(blocks)


def _summarize(hosts: List[Dict]) -> Dict[str, Dict]:
    """{ip: {ports:[sorted], snmp:bool}} — the shape change detection compares."""
    out: Dict[str, Dict] = {}
    for h in hosts:
        ip = h.get("host", "")
        if not ip:
            continue
        out[ip] = {
            "ports": sorted(p["port"] for p in h.get("ports", [])),
            "snmp": bool(h.get("snmp")),
        }
    return out


def _diff_hosts(prev: Dict[str, Dict], curr: Dict[str, Dict]) -> Dict[str, List[str]]:
    """Change events between two summaries: new / down / changed host IPs."""
    new = [ip for ip in curr if ip not in prev]
    down = [ip for ip in prev if ip not in curr]
    changed = [ip for ip in curr if ip in prev and curr[ip] != prev[ip]]
    return {"new": new, "down": down, "changed": changed}


def _configured_cidrs(spec: str) -> List[str]:
    """The CIDR entries (num_addresses > 1) from a targets spec — the ranges the
    operator authorised, used to bound auto-expansion."""
    out: List[str] = []
    for raw in spec.split(","):
        item = raw.strip()
        if not item:
            continue
        try:
            net = ipaddress.ip_network(item, strict=False)
        except ValueError:
            continue
        if net.num_addresses > 1:
            out.append(item)
    return out


def _extract_neighbor_ips(hosts: List[Dict], cidrs: List[str]) -> List[str]:
    """ARP-neighbour IPs (from each host's snmp.arp) that fall INSIDE one of
    ``cidrs`` — safe auto-expansion candidates (never outside authorised ranges)."""
    nets = []
    for c in cidrs:
        try:
            nets.append(ipaddress.ip_network(c, strict=False))
        except ValueError:
            continue
    if not nets:
        return []
    found = set()
    for h in hosts:
        for ip in h.get("snmp", {}).get("arp", {}):
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if any(addr in n for n in nets):
                found.add(ip)
    return sorted(found)
