"""Telegraf config-manager plugin (first-party module plugin).

Responsibility (named for what it does): programmatically **manage the telegraf
configuration** and get telegraf to run with the new config. It owns a delimited
"managed region" of ``telegraf.conf`` (between the two markers) and rewrites only
that region IN-PLACE, so the rest of the hand-maintained config is never touched.

Reload strategy — BOTH, per design:
  1. **watch-config** (happy path): telegraf runs with ``[agent] watch_config="poll"``,
     so writing the file in-place is enough — telegraf re-reads it, no restart.
  2. **restart fallback**: ``reload(force_restart=True)`` restarts the telegraf
     container via the Docker Engine API over the mounted docker socket — for when
     a config reload doesn't take.

This plugin does NOT do network discovery — that is a separate `network` plugin's
job, which would feed discovered targets into this plugin's managed region.

Wiring (docker-compose.yml, plugin-registry service):
  - ``TELEGRAF_CONFIG_PATH`` — writable bind mount of the same telegraf.conf the
    telegraf container reads (``:ro`` there).
  - ``TELEGRAF_CONTAINER`` — container name for the restart fallback.
  - ``/var/run/docker.sock`` — mounted for the restart fallback only.

Note: telegraf.conf is git-tracked; the managed region ships EMPTY. When the plugin
writes inputs into it at runtime the tracked file shows a diff — that is expected
(the committed state is the empty region).
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

__all__ = ["TelegrafPlugin"]

_MARKER_START = "# >>> minder telegraf-plugin managed >>>"
_MARKER_END = "# <<< minder telegraf-plugin managed <<<"

_DEFAULT_CONFIG_PATH = "/app/telegraf-config/telegraf.conf"
_DEFAULT_CONTAINER = "minder-telegraf"
_DOCKER_SOCK = "/var/run/docker.sock"


@dataclass
class PluginMetadata:
    name: str
    version: str
    description: str
    author: str
    dependencies: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    data_sources: List[str] = field(default_factory=list)
    databases: List[str] = field(default_factory=list)
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TelegrafPlugin:
    """Manages the telegraf config's managed region and reloads telegraf."""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.config_path = os.environ.get("TELEGRAF_CONFIG_PATH", _DEFAULT_CONFIG_PATH)
        self.container = os.environ.get("TELEGRAF_CONTAINER", _DEFAULT_CONTAINER)
        self.status = "registered"

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def register(self) -> PluginMetadata:
        return PluginMetadata(
            name="telegraf",
            version="1.0.0",
            description="Manages the telegraf config's managed region and reloads telegraf.",
            author="Minder <core@minder.local>",
            capabilities=["config-management", "reload"],
            data_sources=["telegraf-config"],
            databases=["influxdb"],
        )

    async def initialize(self) -> None:
        # Do NOT mutate the config on init — the markers ship committed, so this is
        # read-only validation (no runtime churn / no git diff unless inputs are
        # actually managed later).
        self.status = "ready"

    async def health_check(self) -> Dict:
        # monitoring.py reads health.get("healthy").
        ok = os.path.isfile(self.config_path) and self._markers_present()
        return {"healthy": bool(ok), "config_path": self.config_path}

    async def collect_data(self) -> Dict:
        """Read-only: report the managed region + telegraf container state."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "config_readable": os.path.isfile(self.config_path),
            "markers_present": self._markers_present(),
            "managed_inputs": self.list_managed_inputs(),
            "telegraf_running": await self._container_running(),
        }

    async def analyze(self) -> Dict:
        inputs = self.list_managed_inputs()
        return {"managed_input_count": len(inputs), "managed_inputs": inputs}

    async def shutdown(self) -> None:
        self.status = "shutdown"

    # ── config management ────────────────────────────────────────────────────
    def _read(self) -> str:
        with open(self.config_path, "r", encoding="utf-8") as f:
            return f.read()

    def _write_inplace(self, text: str) -> None:
        # Truncate + write the SAME inode — critical so the telegraf bind mount
        # keeps seeing the file (a write-rename would break the single-file mount).
        with open(self.config_path, "r+", encoding="utf-8") as f:
            f.seek(0)
            f.write(text)
            f.truncate()

    def _markers_present(self) -> bool:
        try:
            text = self._read()
        except OSError:
            return False
        return _MARKER_START in text and _MARKER_END in text

    def _managed_body(self) -> str:
        text = self._read()
        start = text.index(_MARKER_START) + len(_MARKER_START)
        end = text.index(_MARKER_END)
        return text[start:end]

    def list_managed_inputs(self) -> List[str]:
        """Names of `[[inputs.X]]` blocks currently in the managed region."""
        if not self._markers_present():
            return []
        names = []
        for line in self._managed_body().splitlines():
            s = line.strip()
            if s.startswith("[[inputs.") and s.endswith("]]"):
                names.append(s[len("[[inputs.") : -2])
        return names

    async def set_managed_region(self, body: str, reload: bool = True) -> Dict:
        """Replace everything between the markers with ``body`` (in-place write)."""
        text = self._read()
        if _MARKER_START not in text or _MARKER_END not in text:
            raise RuntimeError("managed-region markers missing from telegraf config")
        head = text[: text.index(_MARKER_START) + len(_MARKER_START)]
        tail = text[text.index(_MARKER_END) :]
        body = body.strip("\n")
        new_text = head + "\n" + (body + "\n" if body else "") + tail
        self._write_inplace(new_text)
        result: Dict = {"written": True, "bytes": len(new_text)}
        if reload:
            result["reload"] = await self.reload()
        return result

    async def clear_managed_region(self, reload: bool = True) -> Dict:
        return await self.set_managed_region("", reload=reload)

    # ── reload: watch-config (happy path) + restart fallback ──────────────────
    async def reload(self, force_restart: bool = False) -> Dict:
        """Get telegraf onto the new config.

        The in-place write already triggers telegraf's watch_config=poll reload;
        that is the happy path and needs nothing here. Pass force_restart=True to
        restart the container instead (fallback for when a reload doesn't take).
        """
        if force_restart:
            restarted = await self._restart_container()
            return {"method": "restart", "restarted": restarted}
        return {"method": "watch-config", "restarted": False}

    # ── docker engine API over the unix socket (httpx, already in the image) ───
    def _docker_client(self) -> httpx.AsyncClient:
        transport = httpx.AsyncHTTPTransport(uds=_DOCKER_SOCK)
        return httpx.AsyncClient(
            transport=transport, base_url="http://docker", timeout=30.0
        )

    async def _container_running(self) -> Optional[bool]:
        try:
            async with self._docker_client() as client:
                r = await client.get(f"/containers/{self.container}/json")
                if r.status_code != 200:
                    return None
                return bool(r.json().get("State", {}).get("Running"))
        except Exception:
            return None

    async def _restart_container(self) -> bool:
        try:
            async with self._docker_client() as client:
                r = await client.post(f"/containers/{self.container}/restart?t=10")
                return r.status_code in (204, 200)
        except Exception:
            return False
