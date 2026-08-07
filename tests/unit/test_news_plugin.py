"""Unit tests for the news plugin (src/plugins/news).

Covers config parsing/apply_config, the RSS/Atom fetch+parse path (mocked httpx,
no real network access), the #370 https-only/public-address URL guard (mocked DNS
resolution), and the registry-driven read/action surface.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

import plugins.news as newsmod
from plugins.news import NewsPlugin, _is_safe_feed_url

_RSS_XML = """<?xml version="1.0"?>
<rss><channel>
  <item><title>Item One</title><link>https://example.com/1</link><pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item>
  <item><title>Item Two</title><link>https://example.com/2</link><pubDate>Tue, 02 Jan 2024 00:00:00 GMT</pubDate></item>
  <item><title></title><link>https://example.com/3</link></item>
</channel></rss>"""

_ATOM_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Atom Item</title>
    <link href="https://example.com/atom1"/>
    <updated>2024-01-01T00:00:00Z</updated>
  </entry>
</feed>"""


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class _FakeAsyncClient:
    """Minimal async-context-manager httpx.AsyncClient stand-in."""

    def __init__(self, text=None, exc=None):
        self._text = text
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kwargs):
        if self._exc:
            raise self._exc
        return _FakeResponse(self._text)

    async def post(self, url, **kwargs):
        if self._exc:
            raise self._exc
        return _FakeResponse(self._text)


class _FakeLoop:
    def __init__(self, addrs=None, error=None):
        self._addrs = addrs or []
        self._error = error

    async def getaddrinfo(self, host, port):
        if self._error:
            raise self._error
        # (family, type, proto, canonname, sockaddr)
        return [(None, None, None, None, (a, 0)) for a in self._addrs]


def _patch_public_dns(monkeypatch, addrs=("93.184.216.34",)):
    monkeypatch.setattr(
        newsmod.asyncio, "get_running_loop", lambda: _FakeLoop(addrs=list(addrs))
    )


# ── _is_safe_feed_url (#370) ────────────────────────────────────────────────
def test_rejects_non_https_scheme(monkeypatch):
    _patch_public_dns(monkeypatch)
    assert asyncio.run(_is_safe_feed_url("http://example.com/rss")) is False
    assert asyncio.run(_is_safe_feed_url("ftp://example.com/rss")) is False


def test_rejects_missing_hostname(monkeypatch):
    _patch_public_dns(monkeypatch)
    assert asyncio.run(_is_safe_feed_url("https:///rss")) is False


def test_accepts_https_public_address(monkeypatch):
    _patch_public_dns(monkeypatch, addrs=("93.184.216.34",))
    assert asyncio.run(_is_safe_feed_url("https://example.com/rss")) is True


@pytest.mark.parametrize(
    "addr",
    [
        "10.0.0.5",  # RFC1918
        "172.16.0.1",  # RFC1918
        "192.168.1.1",  # RFC1918
        "127.0.0.1",  # loopback
        "169.254.169.254",  # link-local / cloud metadata
        "::1",  # loopback (v6)
        "224.0.0.1",  # multicast
    ],
)
def test_rejects_internal_and_special_addresses(monkeypatch, addr):
    _patch_public_dns(monkeypatch, addrs=(addr,))
    assert asyncio.run(_is_safe_feed_url("https://internal.example/rss")) is False


def test_rejects_when_one_of_multiple_resolved_addresses_is_internal(monkeypatch):
    # A hostname resolving to both a public and a private address must be
    # rejected -- allowing it would leak the private-address probe.
    _patch_public_dns(monkeypatch, addrs=("93.184.216.34", "10.0.0.5"))
    assert asyncio.run(_is_safe_feed_url("https://mixed.example/rss")) is False


def test_rejects_on_dns_failure(monkeypatch):
    monkeypatch.setattr(
        newsmod.asyncio,
        "get_running_loop",
        lambda: _FakeLoop(error=OSError("resolution failed")),
    )
    assert asyncio.run(_is_safe_feed_url("https://nonexistent.example/rss")) is False


# ── _parse_feeds ─────────────────────────────────────────────────────────────
def test_parse_feeds_splits_name_and_url_once():
    out = NewsPlugin._parse_feeds("bbc:https://bbc.example/rss,empty:,justname")
    assert out == [("bbc", "https://bbc.example/rss")]


def test_parse_feeds_url_may_contain_colon():
    out = NewsPlugin._parse_feeds("a:https://x.example/rss?x=1:2")
    assert out == [("a", "https://x.example/rss?x=1:2")]


def test_parse_feeds_empty_spec():
    assert NewsPlugin._parse_feeds("") == []


# ── apply_config / __init__ ──────────────────────────────────────────────────
def test_apply_config_maps_all_keys():
    pl = NewsPlugin()
    pl.apply_config(
        {
            "NEWS_FEEDS": "a:https://a.example/rss",
            "NEWS_MAX_ITEMS": "3",
            "NEWS_SINK_INFLUXDB": False,
        }
    )
    assert pl.feeds == [("a", "https://a.example/rss")]
    assert pl.max_items == 3
    assert pl.sink_influxdb is False


def test_apply_config_bad_max_items_falls_back_to_default():
    pl = NewsPlugin()
    pl.apply_config({"NEWS_MAX_ITEMS": "not-a-number"})
    assert pl.max_items == 10


def test_apply_config_sink_influxdb_string_truthy_values():
    pl = NewsPlugin()
    for v in ("1", "true", "yes", "on", "TRUE"):
        pl.apply_config({"NEWS_SINK_INFLUXDB": v})
        assert pl.sink_influxdb is True
    for v in ("0", "false", "no", ""):
        pl.apply_config({"NEWS_SINK_INFLUXDB": v})
        assert pl.sink_influxdb is False


def test_init_default_feeds_are_all_https():
    pl = NewsPlugin()
    assert pl.feeds  # non-empty default mix
    assert all(url.startswith("https://") for _, url in pl.feeds)


# ── lifecycle ────────────────────────────────────────────────────────────────
def test_register_and_health():
    pl = NewsPlugin()
    md = asyncio.run(pl.register())
    assert md.name == "news"
    h = asyncio.run(pl.health_check())
    assert h["healthy"] is True
    assert set(h["feeds"]) == {n for n, _ in pl.feeds}


def test_lifecycle_status_transitions():
    pl = NewsPlugin()
    assert pl.status == "registered"
    asyncio.run(pl.initialize())
    assert pl.status == "ready"
    asyncio.run(pl.shutdown())
    assert pl.status == "shutdown"


# ── _fetch_feed ──────────────────────────────────────────────────────────────
def test_fetch_feed_rejects_unsafe_url_without_making_http_call(monkeypatch):
    called = {"n": 0}

    class _ExplodingClient:
        def __init__(self, *a, **kw):
            called["n"] += 1

    monkeypatch.setattr(newsmod.httpx, "AsyncClient", _ExplodingClient)
    monkeypatch.setattr(newsmod, "_is_safe_feed_url", AsyncMock(return_value=False))
    pl = NewsPlugin()
    items = asyncio.run(pl._fetch_feed("http://internal.example/rss"))
    assert items == []
    assert called["n"] == 0


def test_fetch_feed_parses_rss_items(monkeypatch):
    monkeypatch.setattr(newsmod, "_is_safe_feed_url", AsyncMock(return_value=True))
    monkeypatch.setattr(
        newsmod.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(text=_RSS_XML)
    )
    pl = NewsPlugin()
    items = asyncio.run(pl._fetch_feed("https://example.com/rss"))
    # third <item> has an empty title and is filtered out
    assert [i["title"] for i in items] == ["Item One", "Item Two"]
    assert items[0]["link"] == "https://example.com/1"


def test_fetch_feed_falls_back_to_atom(monkeypatch):
    monkeypatch.setattr(newsmod, "_is_safe_feed_url", AsyncMock(return_value=True))
    monkeypatch.setattr(
        newsmod.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(text=_ATOM_XML)
    )
    pl = NewsPlugin()
    items = asyncio.run(pl._fetch_feed("https://example.com/atom"))
    assert items == [
        {
            "title": "Atom Item",
            "link": "https://example.com/atom1",
            "published": "2024-01-01T00:00:00Z",
        }
    ]


def test_fetch_feed_respects_max_items(monkeypatch):
    monkeypatch.setattr(newsmod, "_is_safe_feed_url", AsyncMock(return_value=True))
    monkeypatch.setattr(
        newsmod.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(text=_RSS_XML)
    )
    pl = NewsPlugin()
    pl.max_items = 1
    items = asyncio.run(pl._fetch_feed("https://example.com/rss"))
    assert len(items) == 1


def test_fetch_feed_returns_empty_on_http_error(monkeypatch):
    monkeypatch.setattr(newsmod, "_is_safe_feed_url", AsyncMock(return_value=True))
    monkeypatch.setattr(
        newsmod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(exc=RuntimeError("boom")),
    )
    pl = NewsPlugin()
    assert asyncio.run(pl._fetch_feed("https://example.com/rss")) == []


def test_fetch_feed_returns_empty_on_malformed_xml(monkeypatch):
    monkeypatch.setattr(newsmod, "_is_safe_feed_url", AsyncMock(return_value=True))
    monkeypatch.setattr(
        newsmod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(text="<not><valid"),
    )
    pl = NewsPlugin()
    assert asyncio.run(pl._fetch_feed("https://example.com/rss")) == []


# ── collect_data / analyze / refresh / get_news ─────────────────────────────
def test_collect_data_aggregates_across_feeds(monkeypatch):
    pl = NewsPlugin()
    pl.feeds = [("a", "https://a.example/rss"), ("b", "https://b.example/rss")]

    async def fake_fetch(url):
        return [{"title": f"from {url}", "link": "", "published": ""}]

    monkeypatch.setattr(pl, "_fetch_feed", fake_fetch)
    monkeypatch.setattr(pl, "_write_influxdb", AsyncMock(return_value=False))
    result = asyncio.run(pl.collect_data())
    assert result["counts"] == {"a": 1, "b": 1}
    assert result["influxdb_written"] is False
    assert pl._last == result


def test_collect_data_skips_feeds_with_no_items(monkeypatch):
    pl = NewsPlugin()
    pl.feeds = [("empty", "https://empty.example/rss")]
    monkeypatch.setattr(pl, "_fetch_feed", AsyncMock(return_value=[]))
    monkeypatch.setattr(pl, "_write_influxdb", AsyncMock(return_value=False))
    result = asyncio.run(pl.collect_data())
    assert result["headlines"] == {}
    assert result["counts"] == {}


def test_analyze_before_any_collection():
    pl = NewsPlugin()
    out = asyncio.run(pl.analyze())
    assert out["message"] == "no data collected yet"


def test_analyze_returns_last_collection(monkeypatch):
    pl = NewsPlugin()
    pl.feeds = [("a", "https://a.example/rss")]
    monkeypatch.setattr(
        pl,
        "_fetch_feed",
        AsyncMock(return_value=[{"title": "t", "link": "", "published": ""}]),
    )
    monkeypatch.setattr(pl, "_write_influxdb", AsyncMock(return_value=False))
    asyncio.run(pl.collect_data())
    assert asyncio.run(pl.analyze()) == pl._last


def test_refresh_calls_collect_data(monkeypatch):
    pl = NewsPlugin()
    monkeypatch.setattr(pl, "collect_data", AsyncMock(return_value={"ok": True}))
    assert asyncio.run(pl.refresh()) == {"ok": True}


def test_get_news_all_feeds(monkeypatch):
    pl = NewsPlugin()
    pl.feeds = [("a", "https://a.example/rss"), ("b", "https://b.example/rss")]

    async def fake_fetch(url):
        name = "a" if "a.example" in url else "b"
        return [{"title": f"{name}-1", "link": "", "published": ""}]

    monkeypatch.setattr(pl, "_fetch_feed", fake_fetch)
    out = asyncio.run(pl.get_news())
    assert out == {"headlines": {"a": ["a-1"], "b": ["b-1"]}}


def test_get_news_filters_to_one_feed(monkeypatch):
    pl = NewsPlugin()
    pl.feeds = [("a", "https://a.example/rss"), ("b", "https://b.example/rss")]
    monkeypatch.setattr(
        pl,
        "_fetch_feed",
        AsyncMock(return_value=[{"title": "x", "link": "", "published": ""}]),
    )
    out = asyncio.run(pl.get_news(feed="a"))
    assert list(out["headlines"].keys()) == ["a"]


def test_get_news_unknown_feed():
    pl = NewsPlugin()
    pl.feeds = [("a", "https://a.example/rss")]
    out = asyncio.run(pl.get_news(feed="nonexistent"))
    assert out["error"] == "unknown feed"
    assert out["available"] == ["a"]


def test_get_news_limit_applied(monkeypatch):
    pl = NewsPlugin()
    pl.feeds = [("a", "https://a.example/rss")]
    monkeypatch.setattr(
        pl,
        "_fetch_feed",
        AsyncMock(
            return_value=[
                {"title": f"t{i}", "link": "", "published": ""} for i in range(10)
            ]
        ),
    )
    out = asyncio.run(pl.get_news(limit=2))
    assert out["headlines"]["a"] == ["t0", "t1"]


def test_get_news_invalid_limit_falls_back_to_default(monkeypatch):
    pl = NewsPlugin()
    pl.feeds = [("a", "https://a.example/rss")]
    monkeypatch.setattr(
        pl,
        "_fetch_feed",
        AsyncMock(
            return_value=[
                {"title": f"t{i}", "link": "", "published": ""} for i in range(10)
            ]
        ),
    )
    out = asyncio.run(pl.get_news(limit="not-a-number"))
    assert len(out["headlines"]["a"]) == 5


# ── _write_influxdb ──────────────────────────────────────────────────────────
def test_write_influxdb_noop_when_sink_disabled():
    pl = NewsPlugin()
    pl.sink_influxdb = False
    pl.config = {"influxdb": {"enabled": True}}
    assert asyncio.run(pl._write_influxdb({"a": 1})) is False


def test_write_influxdb_noop_when_influxdb_not_enabled():
    pl = NewsPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": False}}
    assert asyncio.run(pl._write_influxdb({"a": 1})) is False


def test_write_influxdb_noop_when_counts_empty():
    pl = NewsPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": True}}
    assert asyncio.run(pl._write_influxdb({})) is False


def test_write_influxdb_success(monkeypatch):
    pl = NewsPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": True, "host": "h", "port": 1, "token": "t"}}
    monkeypatch.setattr(
        newsmod.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(text="")
    )
    assert asyncio.run(pl._write_influxdb({"feed a": 3})) is True


def test_write_influxdb_failure_returns_false(monkeypatch):
    pl = NewsPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": True}}
    monkeypatch.setattr(
        newsmod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(exc=RuntimeError("boom")),
    )
    assert asyncio.run(pl._write_influxdb({"a": 1})) is False
