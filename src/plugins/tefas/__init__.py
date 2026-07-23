"""TEFAS fund-price plugin (first-party module plugin).

Backfills daily fund prices from TEFAS (Türkiye Elektronik Fon Alım Satım Platformu)
for the configured fund codes — from a configured start date (or a sane default) up to
today — into InfluxDB (measurement ``tefas_fund_price``, tag ``code``, field ``price``,
one point per publication day). Idempotent + incremental like the crypto plugin: each
run resumes from the latest timestamp already in InfluxDB. Financial data → no gaps /
no double-counting.

Source: the ``tefas-crawler`` library (in the registry image). It's synchronous and
TEFAS rate-limits/robot-checks automated access, so fetches run in a worker thread and
fail soft (a blocked/empty fetch logs a warning and returns nothing rather than
crashing the collection loop). ``borsapy`` is also available in the image (BIST/forex
funds — a yfinance-like API) for a future BIST plugin.

Config is managed centrally over the API (CONFIG_SCHEMA — GET/PUT
/v1/plugins/tefas/config):
  TEFAS_FUNDS        comma-sep TEFAS fund codes (e.g. "AFA,AAK,IPB"); empty = none.
  TEFAS_START_DATE   ISO date to backfill from when InfluxDB is empty (default 2015-01-01).
  TEFAS_SINK_INFLUXDB "1"/"0" — write the series to InfluxDB (default "1").

NOTE: TEFAS actively anti-bots non-Turkish/datacenter egress, so live data-fetch is
only verifiable from an unblocked network (the Pi / a TR ISP). The plugin loads,
configures, and fails soft everywhere; the data lands where TEFAS is reachable.
"""

import asyncio
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import httpx

from plugins._contract import PluginMetadata

__all__ = ["TefasPlugin"]

logger = logging.getLogger("minder.plugin.tefas")

_MEASUREMENT = "tefas_fund_price"
_DEFAULT_START = "2015-01-01"

# NAME COLLISION: this plugin package is `plugins.tefas`, but /app/plugins is on
# sys.path (main.py inserts it), so a bare `import tefas` would resolve to THIS
# directory and shadow the pip `tefas` package (tefas-crawler). Import the library
# with /app/plugins temporarily off the path so the site-package wins, then restore.
_shadow_paths = [p for p in list(sys.path) if p.rstrip("/").endswith("app/plugins")]
for _p in _shadow_paths:
    sys.path.remove(_p)
try:
    from tefas import Crawler

    TEFAS_AVAILABLE = True
except ImportError:  # pragma: no cover
    TEFAS_AVAILABLE = False
    logging.warning("tefas-crawler not installed; TEFAS plugin will no-op")
finally:
    for _p in _shadow_paths:
        sys.path.insert(0, _p)


class TefasPlugin:
    """Backfill + daily-incremental TEFAS fund prices into InfluxDB (tefas-crawler)."""

    ACTIONS = frozenset({"refresh", "get_fund_price"})

    CONFIG_SCHEMA = [
        {
            "key": "TEFAS_FUNDS",
            "type": "string",
            "default": "",
            "description": "TEFAS fund codes to track, comma-separated (e.g. AFA,AAK,IPB).",
        },
        {
            "key": "TEFAS_START_DATE",
            "type": "string",
            "default": _DEFAULT_START,
            "description": "ISO date to backfill from when InfluxDB is empty.",
        },
        {
            "key": "TEFAS_SINK_INFLUXDB",
            "type": "bool",
            "default": True,
            "description": "Write the fund-price series to InfluxDB.",
        },
    ]

    AI_TOOLS = [
        {
            "name": "get_fund_price",
            "description": (
                "Get the latest daily price of a Turkish TEFAS investment fund by its "
                "fund code (e.g. AFA, AAK)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "TEFAS fund code, e.g. 'AFA'.",
                    },
                },
                "required": ["code"],
            },
            "action": "get_fund_price",
        },
    ]

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.http_timeout = float(
            os.environ.get("TEFAS_HTTP_TIMEOUT", "30")
        )  # env-only
        self.status = "registered"
        self._last: Dict = {}
        self.apply_config(
            {
                "TEFAS_FUNDS": os.environ.get("TEFAS_FUNDS", ""),
                "TEFAS_START_DATE": os.environ.get("TEFAS_START_DATE", _DEFAULT_START),
                "TEFAS_SINK_INFLUXDB": os.environ.get("TEFAS_SINK_INFLUXDB", "1"),
            }
        )

    def apply_config(self, cfg: Dict) -> None:
        """Map centrally-managed config → runtime state (no restart). See CONFIG_SCHEMA."""
        if "TEFAS_FUNDS" in cfg:
            self.funds = [
                c.strip().upper()
                for c in str(cfg["TEFAS_FUNDS"] or "").split(",")
                if c.strip()
            ]
        if "TEFAS_START_DATE" in cfg:
            self.start_date = str(cfg["TEFAS_START_DATE"] or _DEFAULT_START).strip()
        if "TEFAS_SINK_INFLUXDB" in cfg:
            v = cfg["TEFAS_SINK_INFLUXDB"]
            self.sink_influxdb = (
                v
                if isinstance(v, bool)
                else str(v).lower() in ("1", "true", "yes", "on")
            )

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def register(self) -> PluginMetadata:
        return PluginMetadata(
            name="tefas",
            version="1.0.0",
            description="Backfills daily TEFAS fund prices into InfluxDB (tefas-crawler).",
            author="Minder <core@minder.local>",
            capabilities=["collect", "analyze", "funds", "backfill"],
            data_sources=["tefas"],
            databases=["influxdb"],
        )

    async def initialize(self) -> None:
        self.status = "ready"

    async def health_check(self) -> Dict:
        # MUST return {"healthy": <bool>} — the monitoring loop reads health["healthy"].
        return {
            "healthy": True,
            "tefas_available": TEFAS_AVAILABLE,
            "funds": self.funds,
            "influxdb_sink": self.sink_influxdb,
        }

    async def shutdown(self) -> None:
        self.status = "shutdown"

    # ── TEFAS fetch (tefas-crawler is sync + anti-botted → to_thread + fail soft) ──
    def _fetch_sync(self, code: str, start: date, end: date) -> List[Tuple[int, float]]:
        """Blocking tefas-crawler fetch → [(unix_seconds, price)]. [] on error/empty."""
        try:
            df = Crawler().fetch(
                start=start.isoformat(),
                end=end.isoformat(),
                name=code,
                columns=["date", "code", "price"],
            )
        except Exception as e:
            logger.warning(f"⚠️ TEFAS fetch failed for {code}: {type(e).__name__}: {e}")
            return []
        out: List[Tuple[int, float]] = []
        try:
            for _, row in df.iterrows():
                d = row["date"]
                day = (
                    d.date() if hasattr(d, "date") else date.fromisoformat(str(d)[:10])
                )
                price = row["price"]
                if price is not None:
                    ts = int(
                        datetime(
                            day.year, day.month, day.day, tzinfo=timezone.utc
                        ).timestamp()
                    )
                    out.append((ts, float(price)))
        except Exception as e:
            logger.warning(f"⚠️ TEFAS parse failed for {code}: {type(e).__name__}")
            return []
        return out

    async def _fetch_history(
        self, code: str, start: date, end: date
    ) -> List[Tuple[int, float]]:
        if not TEFAS_AVAILABLE:
            return []
        return await asyncio.to_thread(self._fetch_sync, code, start, end)

    # ── InfluxDB (mirror crypto: write history + query resume point) ───────────
    def _influx_cfg(self) -> Optional[Dict]:
        cfg = self.config.get("influxdb") or {}
        return cfg if (self.sink_influxdb and cfg.get("enabled")) else None

    async def _latest_influx_date(self, code: str) -> Optional[date]:
        cfg = self._influx_cfg()
        if not cfg:
            return None
        host, port = cfg.get("host", "minder-influxdb"), cfg.get("port", 8086)
        db = cfg.get("bucket", "minder-metrics")
        q = f"SELECT max(time) AS t FROM {_MEASUREMENT} WHERE code = '{code}'"
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                resp = await client.post(
                    f"http://{host}:{port}/api/v3/query_sql",
                    json={"db": db, "q": q, "format": "json"},
                    headers={"Authorization": f"Token {cfg.get('token', '')}"},
                )
                resp.raise_for_status()
                rows = resp.json() or []
        except Exception:
            return None
        t = rows[0].get("t") if rows else None
        if not t:
            return None
        try:
            return datetime.fromisoformat(t.replace("Z", "")).date()
        except ValueError:
            return None

    async def _write_history(self, code: str, points: List[Tuple[int, float]]) -> int:
        cfg = self._influx_cfg()
        if not (cfg and points):
            return 0
        host, port = cfg.get("host", "minder-influxdb"), cfg.get("port", 8086)
        org, bucket = cfg.get("org", "minder"), cfg.get("bucket", "minder-metrics")
        lines = "\n".join(
            f"{_MEASUREMENT},code={code} price={price} {ts}" for ts, price in points
        )
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                resp = await client.post(
                    f"http://{host}:{port}/api/v2/write",
                    params={"org": org, "bucket": bucket, "precision": "s"},
                    headers={"Authorization": f"Token {cfg.get('token', '')}"},
                    content=lines,
                )
                resp.raise_for_status()
            return len(points)
        except Exception as e:
            logger.warning(f"⚠️ InfluxDB write failed for {code}: {type(e).__name__}")
            return 0

    # ── registry-driven reads ────────────────────────────────────────────────
    async def collect_data(self) -> Dict:
        """Backfill/append each fund's daily prices from the resume point to today."""
        today = datetime.now(timezone.utc).date()
        result: Dict[str, Dict] = {}
        for code in self.funds:
            latest = await self._latest_influx_date(code)
            if latest is not None:
                start = latest + timedelta(days=1)
            else:
                try:
                    start = date.fromisoformat(self.start_date)
                except ValueError:
                    start = date.fromisoformat(_DEFAULT_START)
            if start > today:
                result[code] = {"written": 0, "up_to_date": True}
                continue
            points = await self._fetch_history(code, start, today)
            wrote = await self._write_history(code, points)
            result[code] = {
                "written": wrote,
                "from": start.isoformat(),
                "latest_price": points[-1][1] if points else None,
            }
        self._last = {
            "funds": result,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        total = sum(r.get("written", 0) for r in result.values())
        logger.info(f"📊 tefas collect: {total} point(s) across {len(result)} fund(s)")
        return self._last

    async def analyze(self) -> Dict:
        if not self._last:
            return {"message": "no data collected yet", "funds": self.funds}
        return self._last

    # ── actions (POST /v1/plugins/tefas/actions/<method>, JWT-gated) ───────────
    async def refresh(self) -> Dict:
        """Force an immediate backfill/append (same as the hourly loop)."""
        return await self.collect_data()

    async def get_fund_price(self, code: str) -> Dict:
        """Return the latest daily price for a fund code (backs get_fund_price tool)."""
        if not code:
            return {"error": "code is required"}
        code = code.strip().upper()
        today = datetime.now(timezone.utc).date()
        points = await self._fetch_history(code, today - timedelta(days=10), today)
        if not points:
            return {"code": code, "error": "price unavailable"}
        return {"code": code, "price": points[-1][1]}
