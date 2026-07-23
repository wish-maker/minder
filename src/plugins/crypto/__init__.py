"""Cryptocurrency price plugin (first-party module plugin).

Backfills daily close prices for the configured symbols from a public, **keyless**
source (Yahoo Finance) — from the earliest available record (or a configured start
date) up to today — into InfluxDB as a time series (measurement ``crypto_price``, tag
``symbol``, field ``close``, one point per day at that day's timestamp). It is
idempotent + incremental: each run resumes from the latest timestamp already in
InfluxDB (queried via the v3 SQL API), so the first run does the full history and
subsequent (registry-hourly) runs only fetch the new day(s). Financial data, so no
gaps and no double-counting.

``get_price`` is an on-demand action + Ollama tool returning the latest close.

Uses only deps already in the plugin-registry image (``httpx``) — Yahoo over its
public chart API, InfluxDB over its HTTP write (line protocol) + v3 query APIs. No new
dependency, bind-mounted (edit + ``docker restart minder-plugin-registry``).

Config (env on plugin-registry; all optional — keyless defaults):
  CRYPTO_SYMBOLS     Yahoo symbols, comma-sep (default "BTC-USD,ETH-USD"; use e.g.
                     "BTC-EUR" for another quote currency).
  CRYPTO_START_DATE  ISO date (YYYY-MM-DD) to backfill from when InfluxDB is empty;
                     default earliest Yahoo provides.
  CRYPTO_SINK_INFLUXDB "1"/"0" — write to InfluxDB (default "1").
  CRYPTO_HTTP_TIMEOUT  per-request timeout seconds (default 20).
"""

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import httpx

from plugins._contract import PluginMetadata

__all__ = ["CryptoPlugin"]

logger = logging.getLogger("minder.plugin.crypto")

_YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"
# earliest we'll ever ask Yahoo for (it returns from the symbol's real start anyway).
_EARLIEST = date(2010, 1, 1)
# Friendly coin-id → Yahoo symbol aliases for the get_price tool.
_ALIASES = {
    "bitcoin": "BTC-USD",
    "ethereum": "ETH-USD",
    "btc": "BTC-USD",
    "eth": "ETH-USD",
}
_MEASUREMENT = "crypto_price"


class CryptoPlugin:
    """Backfill + daily-incremental crypto close prices (Yahoo, keyless) into InfluxDB."""

    ACTIONS = frozenset({"refresh", "get_price"})

    # Central config (#34) — GET/PUT /v1/plugins/crypto/config, applied live (no restart).
    _DEFAULT_SYMBOLS = "BTC-USD,ETH-USD"
    CONFIG_SCHEMA = [
        {
            "key": "CRYPTO_SYMBOLS",
            "type": "string",
            "default": _DEFAULT_SYMBOLS,
            "description": "Yahoo symbols to backfill, comma-separated (e.g. BTC-USD,ETH-USD,BTC-EUR).",
        },
        {
            "key": "CRYPTO_START_DATE",
            "type": "string",
            "default": "",
            "description": "ISO date to backfill from when InfluxDB is empty; blank = earliest available.",
        },
        {
            "key": "CRYPTO_SINK_INFLUXDB",
            "type": "bool",
            "default": True,
            "description": "Write the price series to InfluxDB.",
        },
    ]

    AI_TOOLS = [
        {
            "name": "get_crypto_price",
            "description": (
                "Get the latest daily close price of a cryptocurrency (e.g. bitcoin, "
                "ethereum, or a Yahoo symbol like BTC-USD)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "coin": {
                        "type": "string",
                        "description": "Coin name/symbol, e.g. 'bitcoin', 'ETH-USD'.",
                    },
                },
                "required": ["coin"],
            },
            "action": "get_price",
        },
    ]

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.http_timeout = float(
            os.environ.get("CRYPTO_HTTP_TIMEOUT", "20")
        )  # env-only
        self.status = "registered"
        self._last: Dict = {}
        # Bootstrap schema-backed config (defaults+env) via the single config→state
        # path; registry re-applies with persisted (API) overrides after load.
        self.apply_config(
            {
                "CRYPTO_SYMBOLS": os.environ.get(
                    "CRYPTO_SYMBOLS", self._DEFAULT_SYMBOLS
                ),
                "CRYPTO_START_DATE": os.environ.get("CRYPTO_START_DATE", ""),
                "CRYPTO_SINK_INFLUXDB": os.environ.get("CRYPTO_SINK_INFLUXDB", "1"),
            }
        )

    def apply_config(self, cfg: Dict) -> None:
        """Map centrally-managed config → runtime state (no restart). See CONFIG_SCHEMA."""
        if "CRYPTO_SYMBOLS" in cfg:
            self.symbols = [
                s.strip().upper()
                for s in str(cfg["CRYPTO_SYMBOLS"] or "").split(",")
                if s.strip()
            ]
        if "CRYPTO_START_DATE" in cfg:
            self.start_date = str(cfg["CRYPTO_START_DATE"] or "").strip()
        if "CRYPTO_SINK_INFLUXDB" in cfg:
            v = cfg["CRYPTO_SINK_INFLUXDB"]
            self.sink_influxdb = (
                v
                if isinstance(v, bool)
                else str(v).lower() in ("1", "true", "yes", "on")
            )

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def register(self) -> PluginMetadata:
        return PluginMetadata(
            name="crypto",
            version="2.0.0",
            description="Backfills daily crypto close prices (Yahoo, keyless) into InfluxDB.",
            author="Minder <core@minder.local>",
            capabilities=["collect", "analyze", "prices", "backfill"],
            data_sources=["yahoo-finance"],
            databases=["influxdb"],
        )

    async def initialize(self) -> None:
        self.status = "ready"

    async def health_check(self) -> Dict:
        # MUST return {"healthy": <bool>} — the monitoring loop reads health["healthy"].
        return {
            "healthy": True,
            "symbols": self.symbols,
            "influxdb_sink": self.sink_influxdb,
        }

    async def shutdown(self) -> None:
        self.status = "shutdown"

    # ── Yahoo Finance history ──────────────────────────────────────────────────
    async def _fetch_history(
        self, symbol: str, start: date, end: date
    ) -> List[Tuple[int, float]]:
        """Return [(unix_seconds, close)] daily points for symbol in [start, end].

        Never raises — returns [] on any API/network error.
        """
        p1 = int(
            datetime(
                start.year, start.month, start.day, tzinfo=timezone.utc
            ).timestamp()
        )
        p2 = (
            int(datetime(end.year, end.month, end.day, tzinfo=timezone.utc).timestamp())
            + 86400
        )
        try:
            async with httpx.AsyncClient(
                timeout=self.http_timeout, headers={"User-Agent": "Mozilla/5.0"}
            ) as client:
                resp = await client.get(
                    _YAHOO_CHART + symbol,
                    params={"period1": p1, "period2": p2, "interval": "1d"},
                )
                resp.raise_for_status()
                res = ((resp.json() or {}).get("chart") or {}).get("result") or []
        except Exception as e:
            logger.warning(
                f"⚠️ Yahoo fetch failed for {symbol}: {type(e).__name__}: {e}"
            )
            return []
        if not res:
            return []
        ts = res[0].get("timestamp") or []
        quote = (res[0].get("indicators") or {}).get("quote") or [{}]
        closes = quote[0].get("close") or []
        out: List[Tuple[int, float]] = []
        for t, c in zip(ts, closes):
            if isinstance(c, (int, float)):
                # normalise to that day's 00:00 UTC so re-runs overwrite, not duplicate.
                day = datetime.fromtimestamp(t, tz=timezone.utc).date()
                out.append(
                    (
                        int(
                            datetime(
                                day.year, day.month, day.day, tzinfo=timezone.utc
                            ).timestamp()
                        ),
                        float(c),
                    )
                )
        return out

    # ── InfluxDB (write history + query resume point) ──────────────────────────
    def _influx_cfg(self) -> Optional[Dict]:
        cfg = self.config.get("influxdb") or {}
        return cfg if (self.sink_influxdb and cfg.get("enabled")) else None

    async def _latest_influx_date(self, symbol: str) -> Optional[date]:
        """Latest day already stored for symbol (v3 SQL query), or None if empty."""
        cfg = self._influx_cfg()
        if not cfg:
            return None
        host, port = cfg.get("host", "minder-influxdb"), cfg.get("port", 8086)
        db = cfg.get("bucket", "minder-metrics")
        q = f"SELECT max(time) AS t FROM {_MEASUREMENT} WHERE symbol = '{symbol}'"
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                resp = await client.post(
                    f"http://{host}:{port}/api/v3/query_sql",
                    json={"db": db, "q": q, "format": "json"},
                    headers={"Authorization": f"Token {cfg.get('token', '')}"},
                )
                resp.raise_for_status()
                rows = resp.json() or []
        except Exception as e:
            logger.warning(
                f"⚠️ InfluxDB resume query failed for {symbol}: {type(e).__name__}"
            )
            return None
        t = rows[0].get("t") if rows else None
        if not t:
            return None
        try:
            return datetime.fromisoformat(t.replace("Z", "")).date()
        except ValueError:
            return None

    async def _write_history(self, symbol: str, points: List[Tuple[int, float]]) -> int:
        """Write [(ts, close)] to InfluxDB; return count written (0 if sink off/empty)."""
        cfg = self._influx_cfg()
        if not (cfg and points):
            return 0
        host, port = cfg.get("host", "minder-influxdb"), cfg.get("port", 8086)
        org, bucket = cfg.get("org", "minder"), cfg.get("bucket", "minder-metrics")
        lines = "\n".join(
            f"{_MEASUREMENT},symbol={symbol} close={close} {ts}" for ts, close in points
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
            logger.warning(f"⚠️ InfluxDB write failed for {symbol}: {type(e).__name__}")
            return 0

    # ── registry-driven reads ────────────────────────────────────────────────
    async def collect_data(self) -> Dict:
        """Backfill/append each symbol's daily closes from the resume point to today."""
        today = datetime.now(timezone.utc).date()
        result: Dict[str, Dict] = {}
        for symbol in self.symbols:
            latest = await self._latest_influx_date(symbol)
            if latest is not None:
                start = latest + timedelta(days=1)  # incremental: only new days
            elif self.start_date:
                try:
                    start = date.fromisoformat(self.start_date)
                except ValueError:
                    start = _EARLIEST
            else:
                start = _EARLIEST  # full history (Yahoo trims to the real start)
            if start > today:
                result[symbol] = {"written": 0, "up_to_date": True}
                continue
            points = await self._fetch_history(symbol, start, today)
            wrote = await self._write_history(symbol, points)
            result[symbol] = {
                "written": wrote,
                "from": start.isoformat(),
                "latest_close": points[-1][1] if points else None,
            }
        self._last = {
            "symbols": result,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        total = sum(r.get("written", 0) for r in result.values())
        logger.info(
            f"💰 crypto collect: {total} point(s) across {len(result)} symbol(s)"
        )
        return self._last

    async def analyze(self) -> Dict:
        """Return the most recent collection summary."""
        if not self._last:
            return {"message": "no data collected yet", "symbols": self.symbols}
        return self._last

    # ── actions (POST /v1/plugins/crypto/actions/<method>, JWT-gated) ──────────
    async def refresh(self) -> Dict:
        """Force an immediate backfill/append (same as the hourly loop)."""
        return await self.collect_data()

    async def get_price(self, coin: str) -> Dict:
        """Return the latest daily close for a coin/symbol (backs get_crypto_price)."""
        if not coin:
            return {"error": "coin is required"}
        key = coin.strip().lower()
        symbol = _ALIASES.get(key, coin.strip().upper())
        if "-" not in symbol:
            symbol = f"{symbol}-USD"
        today = datetime.now(timezone.utc).date()
        points = await self._fetch_history(symbol, today - timedelta(days=7), today)
        if not points:
            return {"symbol": symbol, "error": "price unavailable"}
        return {"symbol": symbol, "close": points[-1][1]}
