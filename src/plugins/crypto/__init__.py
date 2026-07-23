"""Cryptocurrency price plugin (first-party module plugin).

Polls a public, **keyless** price API (CoinGecko by default) for the configured coins
and fans the results into InfluxDB as a time series (measurement ``crypto_price``,
tags ``coin``/``currency``, field ``price``) so Grafana can chart them. The registry
drives ``collect_data`` on its hourly loop; ``get_price`` is exposed as an on-demand
action + an Ollama function-calling tool ("what's the price of bitcoin?").

Uses only deps already in the plugin-registry image (``httpx``) — InfluxDB is written
over its HTTP ``/api/v2/write`` endpoint (line protocol), the same "reach backends over
HTTP, no extra driver" approach as the network plugin. No image rebuild needed: it's
bind-mounted, so edit + ``docker restart minder-plugin-registry``.

Config (env on plugin-registry; all optional — sensible keyless defaults):
  CRYPTO_COINS         comma-sep CoinGecko coin ids (default "bitcoin,ethereum").
  CRYPTO_VS_CURRENCY   quote currency (default "usd").
  CRYPTO_API_BASE      price API base (default CoinGecko simple-price).
  CRYPTO_SINK_INFLUXDB "1"/"0" — write each collection to InfluxDB (default "1").
  CRYPTO_HTTP_TIMEOUT  per-request timeout seconds (default 10).
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from plugins._contract import PluginMetadata

__all__ = ["CryptoPlugin"]

logger = logging.getLogger("minder.plugin.crypto")

_DEFAULT_API = "https://api.coingecko.com/api/v3/simple/price"


class CryptoPlugin:
    """Poll a keyless price API for configured coins; sink the series into InfluxDB."""

    ACTIONS = frozenset({"refresh", "get_price"})

    # Ollama function-calling tools. Each maps to an ACTION (POST
    # /v1/plugins/crypto/actions/<action>); aggregated by GET /v1/plugins/ai/tools.
    AI_TOOLS = [
        {
            "name": "get_crypto_price",
            "description": (
                "Get the current price of a cryptocurrency (e.g. bitcoin, ethereum) "
                "from a public price API."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "coin": {
                        "type": "string",
                        "description": "CoinGecko coin id, e.g. 'bitcoin' or 'ethereum'.",
                    },
                    "currency": {
                        "type": "string",
                        "description": "Quote currency (default 'usd').",
                    },
                },
                "required": ["coin"],
            },
            "action": "get_price",
        },
    ]

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.coins = [
            c.strip()
            for c in os.environ.get("CRYPTO_COINS", "bitcoin,ethereum").split(",")
            if c.strip()
        ]
        self.vs_currency = os.environ.get("CRYPTO_VS_CURRENCY", "usd").strip() or "usd"
        self.api_base = os.environ.get("CRYPTO_API_BASE", _DEFAULT_API)
        self.sink_influxdb = os.environ.get("CRYPTO_SINK_INFLUXDB", "1") == "1"
        self.http_timeout = float(os.environ.get("CRYPTO_HTTP_TIMEOUT", "10"))
        self.status = "registered"
        self._last: Dict = {}

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def register(self) -> PluginMetadata:
        return PluginMetadata(
            name="crypto",
            version="1.0.0",
            description="Polls a keyless crypto price API and stores a time series in InfluxDB.",
            author="Minder <core@minder.local>",
            capabilities=["collect", "analyze", "prices"],
            data_sources=["coingecko"],
            databases=["influxdb"],
        )

    async def initialize(self) -> None:
        self.status = "ready"

    async def health_check(self) -> Dict:
        # MUST return {"healthy": <bool>} — the monitoring loop reads health["healthy"].
        return {
            "healthy": True,
            "coins": self.coins,
            "vs_currency": self.vs_currency,
            "influxdb_sink": self.sink_influxdb,
        }

    async def shutdown(self) -> None:
        self.status = "shutdown"

    # ── price fetching ───────────────────────────────────────────────────────
    async def _fetch_prices(self, coins: List[str]) -> Dict[str, float]:
        """Return {coin: price} for the given coins in the configured currency.

        Never raises — returns {} on any API/network error so a bad poll can't crash
        the registry's collection loop.
        """
        if not coins:
            return {}
        params = {"ids": ",".join(coins), "vs_currencies": self.vs_currency}
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                resp = await client.get(self.api_base, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning(f"⚠️ crypto price fetch failed: {type(e).__name__}: {e}")
            return {}
        prices: Dict[str, float] = {}
        for coin in coins:
            val = (data.get(coin) or {}).get(self.vs_currency)
            if isinstance(val, (int, float)):
                prices[coin] = float(val)
        return prices

    async def _write_influxdb(self, prices: Dict[str, float]) -> bool:
        """Write prices to InfluxDB via the HTTP /api/v2/write API (line protocol)."""
        cfg = self.config.get("influxdb") or {}
        if not (self.sink_influxdb and cfg.get("enabled") and prices):
            return False
        host, port = cfg.get("host", "minder-influxdb"), cfg.get("port", 8086)
        org, bucket = cfg.get("org", "minder"), cfg.get("bucket", "minder-metrics")
        token = cfg.get("token", "")
        lines = "\n".join(
            f"crypto_price,coin={coin},currency={self.vs_currency} price={price}"
            for coin, price in prices.items()
        )
        url = f"http://{host}:{port}/api/v2/write"
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                resp = await client.post(
                    url,
                    params={"org": org, "bucket": bucket, "precision": "s"},
                    headers={"Authorization": f"Token {token}"},
                    content=lines,
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"⚠️ InfluxDB write failed: {type(e).__name__}")
            return False

    # ── registry-driven reads ────────────────────────────────────────────────
    async def collect_data(self) -> Dict:
        """Fetch all configured coins and (optionally) write the series to InfluxDB."""
        prices = await self._fetch_prices(self.coins)
        wrote = await self._write_influxdb(prices)
        self._last = {
            "prices": prices,
            "currency": self.vs_currency,
            "influxdb_written": wrote,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(f"💰 crypto collect: {len(prices)} price(s), influx_written={wrote}")
        return self._last

    async def analyze(self) -> Dict:
        """Return the most recent collection (prices + metadata)."""
        if not self._last:
            return {"message": "no data collected yet", "coins": self.coins}
        return self._last

    # ── actions (POST /v1/plugins/crypto/actions/<method>, JWT-gated) ──────────
    async def refresh(self) -> Dict:
        """Force an immediate re-collection (same as the hourly loop)."""
        return await self.collect_data()

    async def get_price(self, coin: str, currency: Optional[str] = None) -> Dict:
        """Return the current price of a single coin (backs the get_crypto_price tool)."""
        if not coin:
            return {"error": "coin is required"}
        prev = self.vs_currency
        if currency:
            self.vs_currency = currency.strip().lower()
        try:
            prices = await self._fetch_prices([coin.strip().lower()])
        finally:
            self.vs_currency = prev
        price = prices.get(coin.strip().lower())
        if price is None:
            return {"coin": coin, "error": "price unavailable"}
        return {"coin": coin, "currency": currency or self.vs_currency, "price": price}
