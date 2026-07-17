"""Network reference plugin (first-party, no external API keys).

This is the reference implementation of a Minder **module plugin** — a first-party
"fixed handler" that ships in the repo (NOT user-uploaded code, per the platform's
no-arbitrary-code rule). It exercises the full plugin-registry contract end to end:
it is discovered under ``PLUGINS_PATH`` (``/app/plugins``), instantiated with the
storage-config dict, ``register()``/``initialize()``'d at startup, then driven by
the registry's monitoring loops (``health_check`` ~60s, ``collect_data`` hourly).

``collect_data`` measures TCP-connect latency to a few well-known public endpoints
using ONLY the standard library (no raw-socket ping, no third-party deps), so it
runs inside the registry image unchanged and needs no secrets. Persisting the
samples to InfluxDB (the image already ships ``influxdb-client``) is a natural
follow-up; v1 returns/records them in-memory so the load path can be proven first.

Copy this directory as the template for the other plugins (crypto/weather/news/
tefas): keep the same lifecycle methods and the ``PluginMetadata`` return shape.
"""

import asyncio
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

__all__ = ["NetworkPlugin"]


@dataclass
class PluginMetadata:
    """Return shape for ``register()`` — the fields the registry loader reads
    (``core/plugin_loader.py``: name/version/description/author/dependencies/
    capabilities/data_sources/databases/registered_at)."""

    name: str
    version: str
    description: str
    author: str
    dependencies: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    data_sources: List[str] = field(default_factory=list)
    databases: List[str] = field(default_factory=list)
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# (host, port, label) TCP endpoints for a stdlib connectivity probe.
_PROBES = [
    ("1.1.1.1", 53, "cloudflare-dns"),
    ("8.8.8.8", 53, "google-dns"),
]

_CONNECT_TIMEOUT = 3.0  # seconds per probe


class NetworkPlugin:
    """Self-contained network connectivity/latency collector."""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.status = "registered"
        self._last: Dict = {}

    async def register(self) -> PluginMetadata:
        return PluginMetadata(
            name="network",
            version="1.0.0",
            description="Measures TCP-connect latency to public endpoints (stdlib only).",
            author="Minder <core@minder.local>",
            capabilities=["collect", "analyze"],
            data_sources=["tcp-probe"],
            databases=["influxdb"],
        )

    async def initialize(self) -> None:
        self.status = "ready"

    async def health_check(self) -> Dict:
        # The registry's monitoring loop reads the boolean ``healthy`` key
        # (core/monitoring.py: health.get("healthy")).
        return {"healthy": True, "last_run": self._last.get("timestamp")}

    async def _probe(self, host: str, port: int) -> Optional[float]:
        """TCP-connect latency in ms, or None if unreachable (stdlib only)."""
        loop = asyncio.get_event_loop()
        start = time.perf_counter()

        def _connect() -> None:
            socket.create_connection((host, port), timeout=_CONNECT_TIMEOUT).close()

        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, _connect), timeout=_CONNECT_TIMEOUT + 2
            )
            return round((time.perf_counter() - start) * 1000, 2)
        except Exception:
            return None

    async def collect_data(self) -> Dict:
        probes = []
        for host, port, label in _PROBES:
            latency = await self._probe(host, port)
            probes.append(
                {
                    "target": label,
                    "host": host,
                    "port": port,
                    "latency_ms": latency,
                    "reachable": latency is not None,
                }
            )
        self._last = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "probes": probes,
        }
        return self._last

    async def analyze(self) -> Dict:
        probes = self._last.get("probes", [])
        reachable = [p for p in probes if p["reachable"]]
        avg = (
            round(sum(p["latency_ms"] for p in reachable) / len(reachable), 2)
            if reachable
            else None
        )
        return {
            "reachable": len(reachable),
            "total": len(probes),
            "avg_latency_ms": avg,
        }

    async def shutdown(self) -> None:
        self.status = "shutdown"
