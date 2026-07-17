"""Network discovery plugin (first-party module plugin).

Discovers reachable hosts across configured targets with a **stdlib TCP-connect
scan** (no raw sockets, no nmap, no extra deps) and emits ready-to-use telegraf
input config for the live ones. It stays decoupled from the `telegraf` plugin — it
only discovers + reports; it never writes another plugin's state. The composition
is done by the caller:

    GET  /v1/plugins/network/analysis            → live hosts + a `telegraf_config`
    POST /v1/plugins/telegraf/actions/set_managed_region  {"body": <that telegraf_config>}

Config (env on plugin-registry):
  NETWORK_SCAN_TARGETS    comma-separated hosts and/or CIDRs (e.g. "10.0.0.0/28,1.1.1.1").
                          EMPTY by default → scans nothing until configured (safe).
  NETWORK_SCAN_PORT       TCP port to probe (default 80).
  NETWORK_SCAN_MAX_HOSTS  cap on the expanded host count (default 256; a safety bound).

Only scan networks you are authorised to (your own infra) — the empty default
means it does nothing until an operator opts in.
"""

import asyncio
import ipaddress
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from plugins._contract import PluginMetadata

__all__ = ["NetworkPlugin"]

_CONNECT_TIMEOUT = 2.0
_MAX_CONCURRENCY = 64


def _expand_targets(spec: str, max_hosts: int) -> List[str]:
    """Expand a comma-separated hosts/CIDRs spec into individual host strings,
    capped at ``max_hosts``. A bare IP or hostname passes through; a CIDR expands
    to its host addresses."""
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


def _telegraf_config(hosts: List[str], port: int) -> str:
    """Render telegraf `[[inputs.net_response]]` blocks for the given live hosts —
    a body ready to POST to the telegraf plugin's set_managed_region."""
    blocks = []
    for host in hosts:
        blocks.append(
            "[[inputs.net_response]]\n"
            '  protocol = "tcp"\n'
            f'  address = "{host}:{port}"\n'
            '  timeout = "5s"'
        )
    return "\n".join(blocks)


class NetworkPlugin:
    """Self-contained TCP-connect host discovery + telegraf-input emission."""

    # Read-only discovery: no write actions. `scan` runs a scan and returns the
    # result synchronously (vs the background /collect endpoint).
    ACTIONS = frozenset({"scan"})

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.targets = os.environ.get("NETWORK_SCAN_TARGETS", "")
        self.port = int(os.environ.get("NETWORK_SCAN_PORT", "80"))
        self.max_hosts = int(os.environ.get("NETWORK_SCAN_MAX_HOSTS", "256"))
        self.status = "registered"
        self._last: Dict = {}

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def register(self) -> PluginMetadata:
        return PluginMetadata(
            name="network",
            version="1.0.0",
            description="Discovers reachable hosts (stdlib TCP scan) + emits telegraf inputs.",
            author="Minder <core@minder.local>",
            capabilities=["collect", "analyze", "discovery"],
            data_sources=["tcp-scan"],
            databases=["influxdb"],
        )

    async def initialize(self) -> None:
        self.status = "ready"

    async def health_check(self) -> Dict:
        return {"healthy": True, "targets_configured": bool(self.targets.strip())}

    async def _probe(self, host: str, port: int) -> Optional[float]:
        """TCP-connect latency in ms (async, stdlib), or None if unreachable."""
        start = time.perf_counter()
        writer = None
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=_CONNECT_TIMEOUT
            )
            return round((time.perf_counter() - start) * 1000, 2)
        except (OSError, asyncio.TimeoutError):
            return None
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass

    async def collect_data(self) -> Dict:
        """Scan the configured targets and record which hosts are reachable."""
        hosts = _expand_targets(self.targets, self.max_hosts)
        sem = asyncio.Semaphore(_MAX_CONCURRENCY)

        async def _one(host: str) -> Dict:
            async with sem:
                latency = await self._probe(host, self.port)
            return {
                "host": host,
                "port": self.port,
                "reachable": latency is not None,
                "latency_ms": latency,
            }

        results = await asyncio.gather(*[_one(h) for h in hosts]) if hosts else []
        self._last = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "targets": self.targets,
            "scanned": len(results),
            "hosts": results,
        }
        return self._last

    async def scan(self) -> Dict:
        """Action: run a scan now and return the result synchronously."""
        return await self.collect_data()

    async def analyze(self) -> Dict:
        hosts = self._last.get("hosts", [])
        live = [h for h in hosts if h["reachable"]]
        return {
            "live": len(live),
            "scanned": len(hosts),
            "live_hosts": [h["host"] for h in live],
            # ready to POST to /v1/plugins/telegraf/actions/set_managed_region
            "telegraf_config": _telegraf_config([h["host"] for h in live], self.port),
        }

    async def shutdown(self) -> None:
        self.status = "shutdown"
