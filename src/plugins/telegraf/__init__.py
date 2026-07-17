"""Telegraf config-manager plugin (first-party module plugin).

Responsibility (named for what it does): programmatically **manage the telegraf
configuration** and get telegraf to run with the new config. It owns a delimited
"managed region" of ``telegraf.conf`` (between the two markers) and rewrites only
that region IN-PLACE, so the rest of the hand-maintained config is never touched.

Reload strategy — BOTH, per design:
  1. **watch-config** (happy path): telegraf runs with ``--watch-config=poll``, so
     writing the file in-place is enough — telegraf re-reads it, no restart.
  2. **restart fallback**: ``reload(force_restart=True)`` restarts the telegraf
     container via the Docker Engine API over the mounted docker socket.

This plugin does NOT do network discovery — that is a separate `network` plugin's
job, which would feed discovered targets into this plugin's managed region.

Wiring (docker-compose.yml, plugin-registry service):
  - ``TELEGRAF_CONFIG_PATH`` — writable bind mount of the same telegraf.conf the
    telegraf container reads (``:ro`` there).
  - ``TELEGRAF_CONTAINER`` — container name for the restart fallback.
  - ``/var/run/docker.sock`` + ``group_add`` — for the restart fallback only.

Note: telegraf.conf is git-tracked; the managed region ships EMPTY. When the plugin
writes inputs into it at runtime the tracked file shows a diff — that is expected.
"""

import asyncio
import logging
import os
import tomllib
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from plugins._contract import PluginMetadata

__all__ = ["TelegrafPlugin"]

logger = logging.getLogger("minder.plugin.telegraf")

_MARKER_START = "# >>> minder telegraf-plugin managed >>>"
_MARKER_END = "# <<< minder telegraf-plugin managed <<<"

_DEFAULT_CONFIG_PATH = "/app/telegraf-config/telegraf.conf"
_DEFAULT_CONTAINER = "minder-telegraf"
_DOCKER_SOCK = "/var/run/docker.sock"
_DOCKER_TIMEOUT = 10.0  # local unix socket → responds fast; don't stall the loop


class TelegrafPlugin:
    """Manages the telegraf config's managed region and reloads telegraf."""

    # Methods invokable via POST /v1/plugins/telegraf/actions/<name> (JWT-gated).
    # Whitelist only — nothing else on the instance is reachable over HTTP.
    ACTIONS = frozenset({"set_managed_region", "clear_managed_region", "reload"})

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.config_path = os.environ.get("TELEGRAF_CONFIG_PATH", _DEFAULT_CONFIG_PATH)
        self.container = os.environ.get("TELEGRAF_CONTAINER", _DEFAULT_CONTAINER)
        self.status = "registered"
        # Serialise config read+write+reload so concurrent action calls can't
        # interleave and corrupt the in-place write.
        self._lock = asyncio.Lock()

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
        # keeps seeing the file (a write-rename would break the single-file mount,
        # so an atomic temp+rename is deliberately NOT used here). Callers validate
        # the content first (see set_managed_region), so we never write garbage.
        with open(self.config_path, "r+", encoding="utf-8") as f:
            f.seek(0)
            f.write(text)
            f.truncate()

    def _markers_present(self) -> bool:
        try:
            text = self._read()
        except OSError:
            return False
        return text.count(_MARKER_START) == 1 and text.count(_MARKER_END) == 1

    def _split_on_markers(self, text: str) -> "tuple[str, str, str]":
        """Return (head_incl_start, body, tail_incl_end); raises if the markers are
        missing, duplicated, or out of order."""
        if text.count(_MARKER_START) != 1 or text.count(_MARKER_END) != 1:
            raise RuntimeError("telegraf config must have exactly one managed region")
        start = text.index(_MARKER_START) + len(_MARKER_START)
        end = text.index(_MARKER_END)
        if start > end:
            raise RuntimeError("telegraf managed-region markers are out of order")
        return text[:start], text[start:end], text[end:]

    def list_managed_inputs(self) -> List[str]:
        """Names of `[[inputs.X]]` blocks currently in the managed region."""
        try:
            _, body, _ = self._split_on_markers(self._read())
        except (OSError, RuntimeError):
            return []
        names = []
        for line in body.splitlines():
            s = line.strip()
            if s.startswith("[[inputs.") and s.endswith("]]"):
                names.append(s[len("[[inputs.") : -2])
        return names

    async def set_managed_region(self, body: str, reload: bool = True) -> Dict:
        """Replace everything between the markers with ``body`` (validated, in-place).

        ``body`` is validated as TOML before it is written, so a malformed input can
        never reach telegraf and crash-loop it.
        """
        body = body.strip("\n")
        if body:
            try:
                tomllib.loads(body)
            except tomllib.TOMLDecodeError as e:
                raise ValueError(f"managed region body is not valid TOML: {e}") from e
        async with self._lock:
            head, _, tail = self._split_on_markers(self._read())
            new_text = head + "\n" + (body + "\n" if body else "") + tail
            self._write_inplace(new_text)
            result: Dict = {"written": True, "bytes": len(new_text)}
            if reload:
                result["reload"] = await self.reload()
        logger.info(
            "telegraf managed region updated (%d bytes, %d input(s))",
            len(new_text),
            len(self.list_managed_inputs()),
        )
        return result

    async def clear_managed_region(self, reload: bool = True) -> Dict:
        return await self.set_managed_region("", reload=reload)

    # ── reload: watch-config (happy path) + restart fallback ──────────────────
    async def reload(self, force_restart: bool = False) -> Dict:
        """Get telegraf onto the new config.

        The in-place write already triggers telegraf's ``--watch-config=poll``
        reload; that is the happy path and needs nothing here. Pass
        ``force_restart=True`` to restart the container (fallback for when a reload
        doesn't take).
        """
        if force_restart:
            restarted = await self._restart_container()
            return {"method": "restart", "restarted": restarted}
        return {"method": "watch-config", "restarted": False}

    # ── docker engine API over the unix socket (httpx, already in the image) ───
    def _docker_client(self) -> httpx.AsyncClient:
        transport = httpx.AsyncHTTPTransport(uds=_DOCKER_SOCK)
        return httpx.AsyncClient(
            transport=transport, base_url="http://docker", timeout=_DOCKER_TIMEOUT
        )

    async def _container_running(self) -> Optional[bool]:
        try:
            async with self._docker_client() as client:
                r = await client.get(f"/containers/{self.container}/json")
                if r.status_code != 200:
                    logger.warning(
                        "docker inspect %s → HTTP %s", self.container, r.status_code
                    )
                    return None
                return bool(r.json().get("State", {}).get("Running"))
        except Exception as e:  # socket missing/denied, timeout, decode, …
            logger.warning("docker.sock inspect failed: %s: %s", type(e).__name__, e)
            return None

    async def _restart_container(self) -> bool:
        try:
            async with self._docker_client() as client:
                r = await client.post(f"/containers/{self.container}/restart?t=10")
                if r.status_code in (204, 200):
                    return True
                logger.warning(
                    "docker restart %s → HTTP %s", self.container, r.status_code
                )
                return False
        except Exception as e:
            logger.warning("docker.sock restart failed: %s: %s", type(e).__name__, e)
            return False
