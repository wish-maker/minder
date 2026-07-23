"""Weather plugin (first-party module plugin).

Polls a public, **keyless** weather API (Open-Meteo by default) for the configured
locations and sinks the current conditions into InfluxDB as a time series (measurement
``weather``, tag ``location``, fields ``temperature``/``humidity``/``wind_speed``) so
Grafana can chart them. The registry drives ``collect_data`` on its hourly loop;
``get_weather`` is an on-demand action + Ollama tool that resolves any city name via
Open-Meteo's (also keyless) geocoding API.

Uses only deps already in the plugin-registry image (``httpx``) — InfluxDB is written
over its HTTP ``/api/v2/write`` endpoint (line protocol), same as the crypto plugin.
Bind-mounted: edit + ``docker restart minder-plugin-registry``, no image rebuild.

Config (env on plugin-registry; all optional — keyless defaults):
  WEATHER_LOCATIONS    ``name:lat:lon`` triples, comma-sep
                       (default "Istanbul:41.01:28.98,London:51.51:-0.13").
  WEATHER_API_BASE     current-weather API (default Open-Meteo forecast).
  WEATHER_GEOCODE_BASE geocoding API for get_weather by city name (default Open-Meteo).
  WEATHER_SINK_INFLUXDB "1"/"0" — write each collection to InfluxDB (default "1").
  WEATHER_HTTP_TIMEOUT  per-request timeout seconds (default 10).
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import httpx

from plugins._contract import PluginMetadata

__all__ = ["WeatherPlugin"]

logger = logging.getLogger("minder.plugin.weather")

_DEFAULT_API = "https://api.open-meteo.com/v1/forecast"
_DEFAULT_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
_CURRENT_FIELDS = "temperature_2m,relative_humidity_2m,wind_speed_10m"


class WeatherPlugin:
    """Poll a keyless weather API for configured locations; sink the series to InfluxDB."""

    ACTIONS = frozenset({"refresh", "get_weather"})

    AI_TOOLS = [
        {
            "name": "get_weather",
            "description": (
                "Get the current weather (temperature, humidity, wind) for a city by "
                "name, resolved via a public geocoding API."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name, e.g. 'Istanbul', 'Tokyo', 'Berlin'.",
                    },
                },
                "required": ["location"],
            },
            "action": "get_weather",
        },
    ]

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.locations = self._parse_locations(
            os.environ.get(
                "WEATHER_LOCATIONS", "Istanbul:41.01:28.98,London:51.51:-0.13"
            )
        )
        self.api_base = os.environ.get("WEATHER_API_BASE", _DEFAULT_API)
        self.geocode_base = os.environ.get("WEATHER_GEOCODE_BASE", _DEFAULT_GEOCODE)
        self.sink_influxdb = os.environ.get("WEATHER_SINK_INFLUXDB", "1") == "1"
        self.http_timeout = float(os.environ.get("WEATHER_HTTP_TIMEOUT", "10"))
        self.status = "registered"
        self._last: Dict = {}

    @staticmethod
    def _parse_locations(spec: str) -> List[Tuple[str, float, float]]:
        out: List[Tuple[str, float, float]] = []
        for item in spec.split(","):
            parts = item.strip().split(":")
            if len(parts) == 3:
                try:
                    out.append((parts[0].strip(), float(parts[1]), float(parts[2])))
                except ValueError:
                    logger.warning(f"⚠️ bad WEATHER_LOCATIONS entry: {item!r}")
        return out

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def register(self) -> PluginMetadata:
        return PluginMetadata(
            name="weather",
            version="1.0.0",
            description="Polls a keyless weather API and stores a time series in InfluxDB.",
            author="Minder <core@minder.local>",
            capabilities=["collect", "analyze", "weather"],
            data_sources=["open-meteo"],
            databases=["influxdb"],
        )

    async def initialize(self) -> None:
        self.status = "ready"

    async def health_check(self) -> Dict:
        # MUST return {"healthy": <bool>} — the monitoring loop reads health["healthy"].
        return {
            "healthy": True,
            "locations": [name for name, _, _ in self.locations],
            "influxdb_sink": self.sink_influxdb,
        }

    async def shutdown(self) -> None:
        self.status = "shutdown"

    # ── fetching ─────────────────────────────────────────────────────────────
    async def _fetch_current(self, lat: float, lon: float) -> Optional[Dict]:
        """Return {temperature, humidity, wind_speed} for a lat/lon, or None on error."""
        params = {"latitude": lat, "longitude": lon, "current": _CURRENT_FIELDS}
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                resp = await client.get(self.api_base, params=params)
                resp.raise_for_status()
                cur = (resp.json() or {}).get("current") or {}
        except Exception as e:
            logger.warning(f"⚠️ weather fetch failed: {type(e).__name__}: {e}")
            return None
        return {
            "temperature": cur.get("temperature_2m"),
            "humidity": cur.get("relative_humidity_2m"),
            "wind_speed": cur.get("wind_speed_10m"),
        }

    async def _geocode(self, name: str) -> Optional[Tuple[float, float]]:
        """Resolve a city name to (lat, lon) via the keyless geocoding API."""
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                resp = await client.get(
                    self.geocode_base, params={"name": name, "count": 1}
                )
                resp.raise_for_status()
                results = (resp.json() or {}).get("results") or []
        except Exception as e:
            logger.warning(f"⚠️ geocode failed: {type(e).__name__}: {e}")
            return None
        if not results:
            return None
        return results[0].get("latitude"), results[0].get("longitude")

    async def _write_influxdb(self, readings: Dict[str, Dict]) -> bool:
        """Write readings to InfluxDB via the HTTP /api/v2/write API (line protocol)."""
        cfg = self.config.get("influxdb") or {}
        if not (self.sink_influxdb and cfg.get("enabled") and readings):
            return False
        host, port = cfg.get("host", "minder-influxdb"), cfg.get("port", 8086)
        org, bucket = cfg.get("org", "minder"), cfg.get("bucket", "minder-metrics")
        token = cfg.get("token", "")
        lines = []
        for loc, r in readings.items():
            fields = [
                f"{k}={v}"
                for k, v in (
                    ("temperature", r.get("temperature")),
                    ("humidity", r.get("humidity")),
                    ("wind_speed", r.get("wind_speed")),
                )
                if isinstance(v, (int, float))
            ]
            if fields:
                tag = loc.replace(" ", "\\ ")
                lines.append(f"weather,location={tag} {','.join(fields)}")
        if not lines:
            return False
        url = f"http://{host}:{port}/api/v2/write"
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                resp = await client.post(
                    url,
                    params={"org": org, "bucket": bucket, "precision": "s"},
                    headers={"Authorization": f"Token {token}"},
                    content="\n".join(lines),
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"⚠️ InfluxDB write failed: {type(e).__name__}")
            return False

    # ── registry-driven reads ────────────────────────────────────────────────
    async def collect_data(self) -> Dict:
        """Fetch current conditions for all configured locations; sink to InfluxDB."""
        readings: Dict[str, Dict] = {}
        for name, lat, lon in self.locations:
            r = await self._fetch_current(lat, lon)
            if r is not None:
                readings[name] = r
        wrote = await self._write_influxdb(readings)
        self._last = {
            "readings": readings,
            "influxdb_written": wrote,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(f"🌦️ weather collect: {len(readings)} location(s), influx={wrote}")
        return self._last

    async def analyze(self) -> Dict:
        """Return the most recent collection."""
        if not self._last:
            return {
                "message": "no data collected yet",
                "locations": [n for n, _, _ in self.locations],
            }
        return self._last

    # ── actions (POST /v1/plugins/weather/actions/<method>, JWT-gated) ─────────
    async def refresh(self) -> Dict:
        """Force an immediate re-collection (same as the hourly loop)."""
        return await self.collect_data()

    async def get_weather(self, location: str) -> Dict:
        """Current weather for any city by name (backs the get_weather tool)."""
        if not location:
            return {"error": "location is required"}
        coords = await self._geocode(location)
        if not coords or coords[0] is None:
            return {"location": location, "error": "could not resolve location"}
        r = await self._fetch_current(coords[0], coords[1])
        if r is None:
            return {"location": location, "error": "weather unavailable"}
        return {"location": location, **r}
