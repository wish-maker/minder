"""Network discovery plugin (first-party module plugin).

Comprehensive host + service + SNMP discovery of the configured targets:
  - host discovery + port/service/version detection via **nmap** (connect scan
    ``-sT`` — no root; XML parsed with the stdlib). Falls back to a stdlib
    TCP-connect probe if nmap isn't installed;
  - **SNMP OID lookup** of the system group (sysDescr / sysName / sysUpTime / …)
    via net-snmp's ``snmpget`` for hosts that answer on 161;
  - emits ready-to-use telegraf inputs (``net_response`` per open TCP port,
    ``snmp`` per SNMP-capable host).

Decoupled from the telegraf plugin — it only discovers + reports; the composition
is caller-driven: GET this plugin's /analysis → POST the ``telegraf_config`` to
``/v1/plugins/telegraf/actions/set_managed_region``.

Config (env on plugin-registry):
  NETWORK_SCAN_TARGETS    comma-separated hosts and/or CIDRs. EMPTY default →
                          scans nothing until an operator opts in (safe).
  NETWORK_SCAN_PORTS      nmap port spec (default "22,80,161,443,8080").
  NETWORK_SCAN_MAX_HOSTS  cap on the expanded host count (default 256).
  NETWORK_SNMP_ENABLED    "1"/"0" (default "1"; skipped anyway if snmpget absent).
  NETWORK_SNMP_COMMUNITY  SNMP v2c community string (default "public").

Only scan networks you are authorised to (your own infra).
"""

import asyncio
import ipaddress
import os
import shutil
from datetime import datetime, timezone
from typing import Dict, List, Optional
from xml.etree import ElementTree

from plugins._contract import PluginMetadata

__all__ = ["NetworkPlugin"]

_CONNECT_TIMEOUT = 2.0
_MAX_CONCURRENCY = 64
_NMAP_HOST_TIMEOUT = "30s"
_SNMP_TIMEOUT = "2"  # seconds per snmpget

# System-group OIDs (name → oid) fetched from SNMP-capable hosts.
_SNMP_SYSTEM_OIDS = {
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "sysObjectID": "1.3.6.1.2.1.1.2.0",
    "sysUpTime": "1.3.6.1.2.1.1.3.0",
    "sysContact": "1.3.6.1.2.1.1.4.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
    "sysLocation": "1.3.6.1.2.1.1.6.0",
}


# ── pure helpers (unit-tested without any subprocess) ─────────────────────────
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


def _telegraf_config(hosts: List[Dict], snmp_community: str) -> str:
    """Render telegraf inputs for discovered hosts: net_response per open TCP port,
    and an snmp input for each SNMP-capable host."""
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


class NetworkPlugin:
    """nmap + SNMP host/service discovery with a stdlib fallback."""

    # Read-only discovery: `scan` runs a scan and returns the result synchronously.
    ACTIONS = frozenset({"scan"})

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.targets = os.environ.get("NETWORK_SCAN_TARGETS", "")
        self.ports = os.environ.get("NETWORK_SCAN_PORTS", "22,80,161,443,8080")
        self.max_hosts = int(os.environ.get("NETWORK_SCAN_MAX_HOSTS", "256"))
        self.snmp_enabled = os.environ.get("NETWORK_SNMP_ENABLED", "1") == "1"
        self.snmp_community = os.environ.get("NETWORK_SNMP_COMMUNITY", "public")
        self.status = "registered"
        self._last: Dict = {}

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def register(self) -> PluginMetadata:
        return PluginMetadata(
            name="network",
            version="2.0.0",
            description="nmap + SNMP host/service discovery; emits telegraf inputs.",
            author="Minder <core@minder.local>",
            capabilities=["collect", "analyze", "discovery", "snmp"],
            data_sources=["nmap", "snmp"],
            databases=["influxdb"],
        )

    async def initialize(self) -> None:
        self.status = "ready"

    async def health_check(self) -> Dict:
        return {
            "healthy": True,
            "targets_configured": bool(self.targets.strip()),
            "nmap": shutil.which("nmap") is not None,
            "snmp": shutil.which("snmpget") is not None,
        }

    # ── subprocess helper ────────────────────────────────────────────────────
    async def _run(self, *cmd: str, timeout: float = 60.0) -> "tuple[int, str]":
        """Run a command; return (returncode, stdout). Empty on failure/missing."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode or 0, out.decode("utf-8", "replace")
        except (OSError, asyncio.TimeoutError):
            return 1, ""

    # ── discovery backends ───────────────────────────────────────────────────
    async def _nmap_scan(self, hosts: List[str]) -> List[Dict]:
        rc, out = await self._run(
            "nmap",
            "-sT",
            "-sV",
            "-Pn",
            "-p",
            self.ports,
            "--host-timeout",
            _NMAP_HOST_TIMEOUT,
            "-oX",
            "-",
            *hosts,
            timeout=len(hosts) * 45 + 30,
        )
        return _parse_nmap_xml(out) if rc == 0 else []

    async def _tcp_fallback(self, hosts: List[str]) -> List[Dict]:
        """Degraded discovery when nmap is unavailable: stdlib TCP connect to the
        first port in the spec."""
        try:
            port = int(self.ports.split(",")[0])
        except (ValueError, IndexError):
            port = 80
        sem = asyncio.Semaphore(_MAX_CONCURRENCY)

        async def _probe(host: str) -> Dict:
            async with sem:
                writer = None
                open_ = False
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection(host, port), timeout=_CONNECT_TIMEOUT
                    )
                    open_ = True
                except (OSError, asyncio.TimeoutError):
                    open_ = False
                finally:
                    if writer is not None:
                        writer.close()
                        try:
                            await writer.wait_closed()
                        except OSError:
                            pass
            return {
                "host": host,
                "hostname": "",
                "state": "up" if open_ else "down",
                "ports": (
                    [
                        {
                            "port": port,
                            "protocol": "tcp",
                            "service": "",
                            "product": "",
                            "version": "",
                        }
                    ]
                    if open_
                    else []
                ),
            }

        return list(await asyncio.gather(*[_probe(h) for h in hosts]))

    async def _snmp_lookup(self, host: str) -> Dict:
        """Fetch the SNMP system group for a host (empty dict if unreachable)."""
        result: Dict = {}
        for name, oid in _SNMP_SYSTEM_OIDS.items():
            rc, out = await self._run(
                "snmpget",
                "-v2c",
                "-c",
                self.snmp_community,
                "-Ovq",
                "-t",
                _SNMP_TIMEOUT,
                "-r",
                "0",
                host,
                oid,
                timeout=8.0,
            )
            val = out.strip().strip('"')
            if rc == 0 and val and "No Such" not in val:
                result[name] = val
        return result

    # ── orchestration ────────────────────────────────────────────────────────
    async def collect_data(self) -> Dict:
        hosts = _expand_targets(self.targets, self.max_hosts)
        if not hosts:
            self._last = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "targets": self.targets,
                "method": "none",
                "scanned": 0,
                "hosts": [],
            }
            return self._last

        use_nmap = shutil.which("nmap") is not None
        discovered = (
            await self._nmap_scan(hosts)
            if use_nmap
            else await self._tcp_fallback(hosts)
        )

        snmp_capable = self.snmp_enabled and shutil.which("snmpget") is not None
        for h in discovered:
            addr = h.get("host", "")
            has_161 = any(p.get("port") == 161 for p in h.get("ports", []))
            if snmp_capable and addr and (has_161 or not h.get("ports")):
                snmp = await self._snmp_lookup(addr)
                if snmp:
                    h["snmp"] = snmp

        self._last = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "targets": self.targets,
            "method": "nmap" if use_nmap else "tcp-fallback",
            "scanned": len(discovered),
            "hosts": discovered,
        }
        return self._last

    async def scan(self) -> Dict:
        """Action: run a scan now and return the result synchronously."""
        return await self.collect_data()

    async def analyze(self) -> Dict:
        hosts = self._last.get("hosts", [])
        live = [h for h in hosts if h.get("state") == "up" or h.get("ports")]
        return {
            "method": self._last.get("method", "none"),
            "live": len(live),
            "scanned": len(hosts),
            "live_hosts": [h.get("host") for h in live],
            "open_ports": {
                h.get("host"): [p["port"] for p in h.get("ports", [])] for h in live
            },
            "snmp": {h["host"]: h["snmp"] for h in live if h.get("snmp")},
            # ready to POST to /v1/plugins/telegraf/actions/set_managed_region
            "telegraf_config": _telegraf_config(live, self.snmp_community),
        }

    async def shutdown(self) -> None:
        self.status = "shutdown"
