"""News plugin (first-party module plugin).

Fetches headlines from public, **keyless** RSS/Atom feeds (parsed with the stdlib
``xml.etree``), serves the latest items, and writes a per-feed item-count metric into
InfluxDB (measurement ``news``, tag ``feed``, field ``item_count``) so feed volume can
be charted. ``get_news`` is an on-demand action + Ollama tool ("latest headlines?").

Deliberately keyless (RSS, not a paid news API) so it needs no API-key/config decision
and works in any environment. Uses only deps already in the plugin-registry image
(``httpx`` + stdlib ``xml.etree``) — bind-mounted, so edit + ``docker restart
minder-plugin-registry``, no image rebuild.

Config (env on plugin-registry; all optional — keyless defaults):
  NEWS_FEEDS          ``name:url`` pairs, comma-sep (url may contain ':', split once).
                      Default = a broad global + local (Turkish) keyless RSS mix;
                      override per deployment/region via the config API.
  NEWS_MAX_ITEMS      max headlines kept per feed (default 10).
  NEWS_SINK_INFLUXDB  "1"/"0" — write the item-count metric (default "1").
  NEWS_HTTP_TIMEOUT   per-request timeout seconds (default 10).
"""

import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import httpx

from plugins._contract import PluginMetadata

__all__ = ["NewsPlugin"]

logger = logging.getLogger("minder.plugin.news")

# A broad default mix of GLOBAL + LOCAL (Turkish) keyless RSS feeds — all verified
# reachable + parseable from the registry container. Fully overridable per deployment
# via the NEWS_FEEDS config (GET/PUT /v1/plugins/news/config): pick your own region's
# sources. Format is "name:url" pairs (url may contain ':', split once).
_DEFAULT_FEEDS = ",".join(
    [
        # global
        "bbc:http://feeds.bbci.co.uk/news/rss.xml",
        "guardian:https://www.theguardian.com/world/rss",
        "aljazeera:https://www.aljazeera.com/xml/rss/all.xml",
        "hackernews:https://hnrss.org/frontpage",
        "arstechnica:http://feeds.arstechnica.com/arstechnica/index",
        "nasa:https://www.nasa.gov/rss/dyn/breaking_news.rss",
        # local (Turkey)
        "bbc_turkce:https://feeds.bbci.co.uk/turkce/rss.xml",
        "ntv:https://www.ntv.com.tr/gundem.rss",
        "trthaber:https://www.trthaber.com/manset_articles.rss",
        "aa:https://www.aa.com.tr/tr/rss/default?cat=guncel",
        "hurriyet:https://www.hurriyet.com.tr/rss/anasayfa",
    ]
)
_ATOM = "{http://www.w3.org/2005/Atom}"


class NewsPlugin:
    """Fetch headlines from keyless RSS/Atom feeds; serve them + a volume metric."""

    ACTIONS = frozenset({"refresh", "get_news"})

    # Central config (#34) — GET/PUT /v1/plugins/news/config, applied live (no restart).
    CONFIG_SCHEMA = [
        {
            "key": "NEWS_FEEDS",
            "type": "string",
            "default": _DEFAULT_FEEDS,
            "description": "RSS/Atom feeds as 'name:url' pairs, comma-separated.",
        },
        {
            "key": "NEWS_MAX_ITEMS",
            "type": "int",
            "default": 10,
            "description": "Max headlines kept per feed.",
        },
        {
            "key": "NEWS_SINK_INFLUXDB",
            "type": "bool",
            "default": True,
            "description": "Write the per-feed item-count metric to InfluxDB.",
        },
    ]

    AI_TOOLS = [
        {
            "name": "get_news",
            "description": (
                "Get the latest news headlines from the configured RSS feeds, "
                "optionally filtered to one feed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "feed": {
                        "type": "string",
                        "description": "Feed name to filter to (e.g. 'hackernews', 'bbc'). Omit for all.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max headlines to return (default 5).",
                    },
                },
                "required": [],
            },
            "action": "get_news",
        },
    ]

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.http_timeout = float(os.environ.get("NEWS_HTTP_TIMEOUT", "10"))  # env-only
        self.status = "registered"
        self._last: Dict = {}
        # Bootstrap schema-backed config (defaults+env) via the single config→state
        # path; registry re-applies with persisted (API) overrides after load.
        self.apply_config(
            {
                "NEWS_FEEDS": os.environ.get("NEWS_FEEDS", _DEFAULT_FEEDS),
                "NEWS_MAX_ITEMS": os.environ.get("NEWS_MAX_ITEMS", "10"),
                "NEWS_SINK_INFLUXDB": os.environ.get("NEWS_SINK_INFLUXDB", "1"),
            }
        )

    def apply_config(self, cfg: Dict) -> None:
        """Map centrally-managed config → runtime state (no restart). See CONFIG_SCHEMA."""
        if "NEWS_FEEDS" in cfg:
            self.feeds = self._parse_feeds(str(cfg["NEWS_FEEDS"] or ""))
        if "NEWS_MAX_ITEMS" in cfg:
            try:
                self.max_items = int(cfg["NEWS_MAX_ITEMS"])
            except (TypeError, ValueError):
                self.max_items = 10
        if "NEWS_SINK_INFLUXDB" in cfg:
            v = cfg["NEWS_SINK_INFLUXDB"]
            self.sink_influxdb = (
                v
                if isinstance(v, bool)
                else str(v).lower() in ("1", "true", "yes", "on")
            )

    @staticmethod
    def _parse_feeds(spec: str) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        for item in spec.split(","):
            name, sep, url = item.strip().partition(":")
            if sep and name and url.strip():
                out.append((name.strip(), url.strip()))
        return out

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def register(self) -> PluginMetadata:
        return PluginMetadata(
            name="news",
            version="1.0.0",
            description="Fetches headlines from keyless RSS feeds; item-count series in InfluxDB.",
            author="Minder <core@minder.local>",
            capabilities=["collect", "analyze", "news"],
            data_sources=["rss"],
            databases=["influxdb"],
        )

    async def initialize(self) -> None:
        self.status = "ready"

    async def health_check(self) -> Dict:
        # MUST return {"healthy": <bool>} — the monitoring loop reads health["healthy"].
        return {
            "healthy": True,
            "feeds": [name for name, _ in self.feeds],
            "influxdb_sink": self.sink_influxdb,
        }

    async def shutdown(self) -> None:
        self.status = "shutdown"

    # ── fetching / parsing ─────────────────────────────────────────────────────
    async def _fetch_feed(self, url: str) -> List[Dict]:
        """Fetch + parse one RSS/Atom feed into [{title, link, published}]. [] on error."""
        try:
            async with httpx.AsyncClient(
                timeout=self.http_timeout, follow_redirects=True
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
            root = ET.fromstring(resp.text)
        except Exception as e:
            logger.warning(f"⚠️ news fetch/parse failed for {url}: {type(e).__name__}")
            return []
        items: List[Dict] = []
        # RSS 2.0: channel/item
        for it in root.findall(".//item"):
            items.append(
                {
                    "title": (it.findtext("title") or "").strip(),
                    "link": (it.findtext("link") or "").strip(),
                    "published": (it.findtext("pubDate") or "").strip(),
                }
            )
        # Atom fallback: feed/entry
        if not items:
            for it in root.findall(f".//{_ATOM}entry"):
                link_el = it.find(f"{_ATOM}link")
                items.append(
                    {
                        "title": (it.findtext(f"{_ATOM}title") or "").strip(),
                        "link": link_el.get("href", "") if link_el is not None else "",
                        "published": (it.findtext(f"{_ATOM}updated") or "").strip(),
                    }
                )
        return [i for i in items if i["title"]][: self.max_items]

    async def _write_influxdb(self, counts: Dict[str, int]) -> bool:
        """Write per-feed item counts to InfluxDB (measurement 'news')."""
        cfg = self.config.get("influxdb") or {}
        if not (self.sink_influxdb and cfg.get("enabled") and counts):
            return False
        host, port = cfg.get("host", "minder-influxdb"), cfg.get("port", 8086)
        org, bucket = cfg.get("org", "minder"), cfg.get("bucket", "minder-metrics")
        token = cfg.get("token", "")
        rows = []
        for feed, n in counts.items():
            tag = feed.replace(" ", "\\ ")  # escape spaces in the line-protocol tag
            rows.append(f"news,feed={tag} item_count={n}i")
        lines = "\n".join(rows)
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
        """Fetch all configured feeds; store headlines + write the volume metric."""
        headlines: Dict[str, List[Dict]] = {}
        for name, url in self.feeds:
            items = await self._fetch_feed(url)
            if items:
                headlines[name] = items
        counts = {feed: len(items) for feed, items in headlines.items()}
        wrote = await self._write_influxdb(counts)
        self._last = {
            "headlines": headlines,
            "counts": counts,
            "influxdb_written": wrote,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(
            f"📰 news collect: {sum(counts.values())} items across {len(counts)} feed(s)"
        )
        return self._last

    async def analyze(self) -> Dict:
        """Return the most recent collection."""
        if not self._last:
            return {
                "message": "no data collected yet",
                "feeds": [n for n, _ in self.feeds],
            }
        return self._last

    # ── actions (POST /v1/plugins/news/actions/<method>, JWT-gated) ────────────
    async def refresh(self) -> Dict:
        """Force an immediate re-collection (same as the hourly loop)."""
        return await self.collect_data()

    async def get_news(self, feed: Optional[str] = None, limit: int = 5) -> Dict:
        """Return the latest headlines (optionally for one feed). Backs the get_news tool."""
        try:
            limit = max(1, int(limit))
        except (TypeError, ValueError):
            limit = 5
        targets = [(n, u) for n, u in self.feeds if (not feed or n == feed)]
        if not targets:
            return {
                "feed": feed,
                "error": "unknown feed",
                "available": [n for n, _ in self.feeds],
            }
        out: Dict[str, List[str]] = {}
        for name, url in targets:
            items = await self._fetch_feed(url)
            out[name] = [i["title"] for i in items[:limit]]
        return {"headlines": out}
