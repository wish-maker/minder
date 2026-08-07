"""Unit tests for the crypto plugin (src/plugins/crypto).

Covers config parsing/apply_config, the Yahoo Finance chart-JSON fetch+parse path
(mocked httpx, no real network access), the InfluxDB resume-point query + write
paths (including the #215 L3 _SAFE_SYMBOL guard actually being *consulted*, not just
defined), and — per issue #371 — thorough coverage of collect_data's
backfill-vs-append date-window branching, which is the most state-dependent and
error-prone part of this plugin.
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

import plugins.crypto as cryptomod
from plugins.crypto import _ALIASES, _EARLIEST, _SAFE_SYMBOL, CryptoPlugin


class _FakeResponse:
    def __init__(self, json_data=None):
        self._json = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


class _FakeAsyncClient:
    """Minimal async-context-manager httpx.AsyncClient stand-in."""

    def __init__(self, json_data=None, exc=None):
        self._json = json_data
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kwargs):
        if self._exc:
            raise self._exc
        return _FakeResponse(self._json)

    async def post(self, url, **kwargs):
        if self._exc:
            raise self._exc
        return _FakeResponse(self._json)


def _yahoo_json(timestamps, closes):
    return {
        "chart": {
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {"quote": [{"close": closes}]},
                }
            ]
        }
    }


def _day0(y, m, d):
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())


# ── apply_config / __init__ ──────────────────────────────────────────────────
def test_apply_config_symbols_comma_split_upper_blank_dropped():
    pl = CryptoPlugin()
    pl.apply_config({"CRYPTO_SYMBOLS": " btc-usd ,, eth-usd, "})
    assert pl.symbols == ["BTC-USD", "ETH-USD"]


def test_apply_config_start_date_passthrough():
    pl = CryptoPlugin()
    pl.apply_config({"CRYPTO_START_DATE": " 2020-05-01 "})
    assert pl.start_date == "2020-05-01"


def test_apply_config_sink_influxdb_string_truthy_values():
    pl = CryptoPlugin()
    for v in ("1", "true", "yes", "on", "TRUE"):
        pl.apply_config({"CRYPTO_SINK_INFLUXDB": v})
        assert pl.sink_influxdb is True
    for v in ("0", "false", "no", ""):
        pl.apply_config({"CRYPTO_SINK_INFLUXDB": v})
        assert pl.sink_influxdb is False


def test_apply_config_sink_influxdb_bool_passthrough():
    pl = CryptoPlugin()
    pl.apply_config({"CRYPTO_SINK_INFLUXDB": True})
    assert pl.sink_influxdb is True
    pl.apply_config({"CRYPTO_SINK_INFLUXDB": False})
    assert pl.sink_influxdb is False


def test_init_defaults():
    pl = CryptoPlugin()
    assert pl.symbols == ["BTC-USD", "ETH-USD"]
    assert pl.start_date == ""
    assert pl.sink_influxdb is True


# ── lifecycle ────────────────────────────────────────────────────────────────
def test_register_and_health():
    pl = CryptoPlugin()
    md = asyncio.run(pl.register())
    assert md.name == "crypto"
    h = asyncio.run(pl.health_check())
    assert h["healthy"] is True
    assert h["symbols"] == pl.symbols
    assert h["influxdb_sink"] is pl.sink_influxdb


def test_lifecycle_status_transitions():
    pl = CryptoPlugin()
    assert pl.status == "registered"
    asyncio.run(pl.initialize())
    assert pl.status == "ready"
    asyncio.run(pl.shutdown())
    assert pl.status == "shutdown"


# ── _fetch_history ───────────────────────────────────────────────────────────
def test_fetch_history_parses_and_normalizes_skips_non_numeric(monkeypatch):
    ts = [
        _day0(2024, 1, 10) + 14 * 3600,  # mid-day on the 10th
        _day0(2024, 1, 11) + 9 * 3600,  # mid-day on the 11th (bad close)
        _day0(2024, 1, 12) + 1 * 3600,  # mid-day on the 12th
    ]
    closes = [100.5, "bad", 102.25]
    monkeypatch.setattr(
        cryptomod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(json_data=_yahoo_json(ts, closes)),
    )
    pl = CryptoPlugin()
    out = asyncio.run(
        pl._fetch_history("BTC-USD", date(2024, 1, 10), date(2024, 1, 12))
    )
    assert out == [
        (_day0(2024, 1, 10), 100.5),
        (_day0(2024, 1, 12), 102.25),
    ]


@pytest.mark.parametrize(
    "json_data",
    [
        {},
        {"chart": {}},
        {"chart": {"result": []}},
        {"chart": {"result": None}},
    ],
)
def test_fetch_history_empty_or_missing_result(monkeypatch, json_data):
    monkeypatch.setattr(
        cryptomod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(json_data=json_data),
    )
    pl = CryptoPlugin()
    out = asyncio.run(pl._fetch_history("BTC-USD", date(2024, 1, 1), date(2024, 1, 2)))
    assert out == []


def test_fetch_history_returns_empty_on_http_exception(monkeypatch):
    monkeypatch.setattr(
        cryptomod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(exc=RuntimeError("boom")),
    )
    pl = CryptoPlugin()
    out = asyncio.run(pl._fetch_history("BTC-USD", date(2024, 1, 1), date(2024, 1, 2)))
    assert out == []


# ── _influx_cfg ──────────────────────────────────────────────────────────────
def test_influx_cfg_none_when_sink_disabled():
    pl = CryptoPlugin()
    pl.sink_influxdb = False
    pl.config = {"influxdb": {"enabled": True}}
    assert pl._influx_cfg() is None


def test_influx_cfg_none_when_influxdb_not_enabled():
    pl = CryptoPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": False}}
    assert pl._influx_cfg() is None


def test_influx_cfg_none_when_influxdb_config_missing():
    pl = CryptoPlugin()
    pl.sink_influxdb = True
    pl.config = {}
    assert pl._influx_cfg() is None


def test_influx_cfg_returns_cfg_when_enabled():
    pl = CryptoPlugin()
    pl.sink_influxdb = True
    cfg = {"enabled": True, "host": "h", "port": 1}
    pl.config = {"influxdb": cfg}
    assert pl._influx_cfg() is cfg


# ── _latest_influx_date ──────────────────────────────────────────────────────
def test_latest_influx_date_none_when_cfg_missing():
    pl = CryptoPlugin()
    pl.sink_influxdb = False
    assert asyncio.run(pl._latest_influx_date("BTC-USD")) is None


def test_latest_influx_date_unsafe_symbol_skips_http_call_and_warns(
    monkeypatch, caplog
):
    called = {"n": 0}

    class _ExplodingClient:
        def __init__(self, *a, **kw):
            called["n"] += 1

    monkeypatch.setattr(cryptomod.httpx, "AsyncClient", _ExplodingClient)
    pl = CryptoPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": True}}
    unsafe = "BTC'; DROP TABLE x --"
    assert not _SAFE_SYMBOL.match(unsafe)
    with caplog.at_level("WARNING"):
        out = asyncio.run(pl._latest_influx_date(unsafe))
    assert out is None
    assert called["n"] == 0
    assert any("unsafe symbol" in r.message for r in caplog.records)


@pytest.mark.parametrize(
    "t_value, expected",
    [
        ("2024-01-15T00:00:00", date(2024, 1, 15)),
        ("2024-01-15T00:00:00Z", date(2024, 1, 15)),
    ],
)
def test_latest_influx_date_parses_iso_date(monkeypatch, t_value, expected):
    monkeypatch.setattr(
        cryptomod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(json_data=[{"t": t_value}]),
    )
    pl = CryptoPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": True}}
    assert asyncio.run(pl._latest_influx_date("BTC-USD")) == expected


@pytest.mark.parametrize("rows", [[], [{"t": None}], [{"t": ""}], [{}]])
def test_latest_influx_date_none_when_rows_empty_or_t_falsy(monkeypatch, rows):
    monkeypatch.setattr(
        cryptomod.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(json_data=rows)
    )
    pl = CryptoPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": True}}
    assert asyncio.run(pl._latest_influx_date("BTC-USD")) is None


def test_latest_influx_date_none_on_http_exception(monkeypatch):
    monkeypatch.setattr(
        cryptomod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(exc=RuntimeError("boom")),
    )
    pl = CryptoPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": True}}
    assert asyncio.run(pl._latest_influx_date("BTC-USD")) is None


def test_latest_influx_date_none_on_unparseable_timestamp(monkeypatch):
    monkeypatch.setattr(
        cryptomod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(json_data=[{"t": "not-a-date"}]),
    )
    pl = CryptoPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": True}}
    assert asyncio.run(pl._latest_influx_date("BTC-USD")) is None


# ── _write_history ───────────────────────────────────────────────────────────
def test_write_history_zero_when_cfg_none():
    pl = CryptoPlugin()
    pl.sink_influxdb = False
    assert asyncio.run(pl._write_history("BTC-USD", [(1, 2.0)])) == 0


def test_write_history_zero_when_points_empty():
    pl = CryptoPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": True}}
    assert asyncio.run(pl._write_history("BTC-USD", [])) == 0


def test_write_history_unsafe_symbol_skips_http_call_and_warns(monkeypatch, caplog):
    called = {"n": 0}

    class _ExplodingClient:
        def __init__(self, *a, **kw):
            called["n"] += 1

    monkeypatch.setattr(cryptomod.httpx, "AsyncClient", _ExplodingClient)
    pl = CryptoPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": True}}
    unsafe = "BTC'; DROP TABLE x --"
    assert not _SAFE_SYMBOL.match(unsafe)
    with caplog.at_level("WARNING"):
        out = asyncio.run(pl._write_history(unsafe, [(1, 2.0)]))
    assert out == 0
    assert called["n"] == 0
    assert any("unsafe symbol" in r.message for r in caplog.records)


def test_write_history_success_returns_point_count(monkeypatch):
    monkeypatch.setattr(
        cryptomod.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(json_data="")
    )
    pl = CryptoPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": True, "host": "h", "port": 1}}
    points = [(1704844800, 100.0), (1704931200, 101.5)]
    assert asyncio.run(pl._write_history("BTC-USD", points)) == len(points)


def test_write_history_zero_on_http_exception(monkeypatch):
    monkeypatch.setattr(
        cryptomod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(exc=RuntimeError("boom")),
    )
    pl = CryptoPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": True}}
    assert asyncio.run(pl._write_history("BTC-USD", [(1, 2.0)])) == 0


# ── collect_data — the state-dependent backfill-vs-append branching (#371) ──
def _today():
    return datetime.now(timezone.utc).date()


def test_collect_data_incremental_append_from_latest_plus_one_day(monkeypatch):
    pl = CryptoPlugin()
    pl.symbols = ["BTC-USD"]
    yesterday = _today() - timedelta(days=1)

    fetch_calls = []

    async def fake_latest(symbol):
        return yesterday

    async def fake_fetch(symbol, start, end):
        fetch_calls.append((symbol, start, end))
        return [(1, 42.0)]

    async def fake_write(symbol, points):
        return len(points)

    monkeypatch.setattr(pl, "_latest_influx_date", fake_latest)
    monkeypatch.setattr(pl, "_fetch_history", fake_fetch)
    monkeypatch.setattr(pl, "_write_history", fake_write)

    result = asyncio.run(pl.collect_data())

    assert fetch_calls == [("BTC-USD", _today(), _today())]
    assert result["symbols"]["BTC-USD"]["from"] == _today().isoformat()
    assert result["symbols"]["BTC-USD"]["written"] == 1
    assert result["symbols"]["BTC-USD"]["latest_close"] == 42.0
    assert "up_to_date" not in result["symbols"]["BTC-USD"]


def test_collect_data_up_to_date_when_incremental_start_is_in_the_future(monkeypatch):
    pl = CryptoPlugin()
    pl.symbols = ["BTC-USD"]

    async def fake_latest(symbol):
        return _today()  # start = today+1 > today

    fetch_called = {"n": 0}

    async def fake_fetch(symbol, start, end):
        fetch_called["n"] += 1
        return [(1, 42.0)]

    monkeypatch.setattr(pl, "_latest_influx_date", fake_latest)
    monkeypatch.setattr(pl, "_fetch_history", fake_fetch)
    monkeypatch.setattr(pl, "_write_history", AsyncMock(return_value=0))

    result = asyncio.run(pl.collect_data())

    assert fetch_called["n"] == 0
    assert result["symbols"]["BTC-USD"] == {"written": 0, "up_to_date": True}


def test_collect_data_uses_configured_start_date_when_no_influx_history(monkeypatch):
    pl = CryptoPlugin()
    pl.symbols = ["BTC-USD"]
    pl.start_date = "2019-06-15"

    fetch_calls = []

    async def fake_fetch(symbol, start, end):
        fetch_calls.append(start)
        return []

    monkeypatch.setattr(pl, "_latest_influx_date", AsyncMock(return_value=None))
    monkeypatch.setattr(pl, "_fetch_history", fake_fetch)
    monkeypatch.setattr(pl, "_write_history", AsyncMock(return_value=0))

    result = asyncio.run(pl.collect_data())

    assert fetch_calls == [date(2019, 6, 15)]
    assert result["symbols"]["BTC-USD"]["from"] == "2019-06-15"


def test_collect_data_falls_back_to_earliest_when_start_date_invalid(monkeypatch):
    pl = CryptoPlugin()
    pl.symbols = ["BTC-USD"]
    pl.start_date = "not-a-date"

    fetch_calls = []

    async def fake_fetch(symbol, start, end):
        fetch_calls.append(start)
        return []

    monkeypatch.setattr(pl, "_latest_influx_date", AsyncMock(return_value=None))
    monkeypatch.setattr(pl, "_fetch_history", fake_fetch)
    monkeypatch.setattr(pl, "_write_history", AsyncMock(return_value=0))

    result = asyncio.run(pl.collect_data())

    assert fetch_calls == [_EARLIEST]
    assert result["symbols"]["BTC-USD"]["from"] == _EARLIEST.isoformat()


def test_collect_data_falls_back_to_earliest_when_start_date_empty(monkeypatch):
    pl = CryptoPlugin()
    pl.symbols = ["BTC-USD"]
    pl.start_date = ""

    fetch_calls = []

    async def fake_fetch(symbol, start, end):
        fetch_calls.append(start)
        return []

    monkeypatch.setattr(pl, "_latest_influx_date", AsyncMock(return_value=None))
    monkeypatch.setattr(pl, "_fetch_history", fake_fetch)
    monkeypatch.setattr(pl, "_write_history", AsyncMock(return_value=0))

    result = asyncio.run(pl.collect_data())

    assert fetch_calls == [_EARLIEST]
    assert result["symbols"]["BTC-USD"]["from"] == _EARLIEST.isoformat()


def test_collect_data_aggregates_across_symbols_independently(monkeypatch):
    pl = CryptoPlugin()
    pl.symbols = ["BTC-USD", "ETH-USD"]
    pl.start_date = ""

    latest_map = {"BTC-USD": None, "ETH-USD": date(2024, 1, 1)}
    fetch_map = {
        "BTC-USD": [(1, 10.0), (2, 11.0)],
        "ETH-USD": [],
    }
    write_map = {"BTC-USD": 2, "ETH-USD": 0}

    async def fake_latest(symbol):
        return latest_map[symbol]

    async def fake_fetch(symbol, start, end):
        return fetch_map[symbol]

    async def fake_write(symbol, points):
        return write_map[symbol]

    monkeypatch.setattr(pl, "_latest_influx_date", fake_latest)
    monkeypatch.setattr(pl, "_fetch_history", fake_fetch)
    monkeypatch.setattr(pl, "_write_history", fake_write)

    result = asyncio.run(pl.collect_data())

    assert result["symbols"]["BTC-USD"]["from"] == _EARLIEST.isoformat()
    assert result["symbols"]["BTC-USD"]["written"] == 2
    assert result["symbols"]["BTC-USD"]["latest_close"] == 11.0

    assert result["symbols"]["ETH-USD"]["from"] == date(2024, 1, 2).isoformat()
    assert result["symbols"]["ETH-USD"]["written"] == 0
    assert result["symbols"]["ETH-USD"]["latest_close"] is None

    assert set(result["symbols"]) == {"BTC-USD", "ETH-USD"}
    assert pl._last == result


def test_collect_data_sets_last_with_symbols_and_collected_at(monkeypatch):
    pl = CryptoPlugin()
    pl.symbols = ["BTC-USD"]
    pl.start_date = ""
    monkeypatch.setattr(pl, "_latest_influx_date", AsyncMock(return_value=None))
    monkeypatch.setattr(pl, "_fetch_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(pl, "_write_history", AsyncMock(return_value=0))

    result = asyncio.run(pl.collect_data())

    assert set(result.keys()) == {"symbols", "collected_at"}
    assert "BTC-USD" in result["symbols"]
    # collected_at must be a real, parseable ISO timestamp
    datetime.fromisoformat(result["collected_at"])
    assert pl._last == result


# ── analyze / refresh ────────────────────────────────────────────────────────
def test_analyze_before_any_collection():
    pl = CryptoPlugin()
    out = asyncio.run(pl.analyze())
    assert out["message"] == "no data collected yet"
    assert out["symbols"] == pl.symbols


def test_analyze_returns_last_collection(monkeypatch):
    pl = CryptoPlugin()
    pl.symbols = ["BTC-USD"]
    monkeypatch.setattr(pl, "_latest_influx_date", AsyncMock(return_value=None))
    monkeypatch.setattr(pl, "_fetch_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(pl, "_write_history", AsyncMock(return_value=0))
    asyncio.run(pl.collect_data())
    assert asyncio.run(pl.analyze()) == pl._last


def test_refresh_calls_collect_data(monkeypatch):
    pl = CryptoPlugin()
    monkeypatch.setattr(pl, "collect_data", AsyncMock(return_value={"ok": True}))
    assert asyncio.run(pl.refresh()) == {"ok": True}


# ── get_price ────────────────────────────────────────────────────────────────
def test_get_price_empty_coin_returns_error():
    pl = CryptoPlugin()
    assert asyncio.run(pl.get_price("")) == {"error": "coin is required"}


@pytest.mark.parametrize(
    "coin, expected_symbol",
    [
        ("bitcoin", "BTC-USD"),
        ("Bitcoin", "BTC-USD"),
        ("btc", "BTC-USD"),
        ("eth", "ETH-USD"),
        ("ethereum", "ETH-USD"),
    ],
)
def test_get_price_alias_resolution(monkeypatch, coin, expected_symbol):
    pl = CryptoPlugin()
    seen = {}

    async def fake_fetch(symbol, start, end):
        seen["symbol"] = symbol
        return [(1, 1.0)]

    monkeypatch.setattr(pl, "_fetch_history", fake_fetch)
    asyncio.run(pl.get_price(coin))
    assert seen["symbol"] == expected_symbol
    assert _ALIASES[coin.strip().lower()] == expected_symbol


def test_get_price_bare_symbol_gets_usd_suffix(monkeypatch):
    pl = CryptoPlugin()
    seen = {}

    async def fake_fetch(symbol, start, end):
        seen["symbol"] = symbol
        return [(1, 5.0)]

    monkeypatch.setattr(pl, "_fetch_history", fake_fetch)
    out = asyncio.run(pl.get_price("sol"))
    assert seen["symbol"] == "SOL-USD"
    assert out == {"symbol": "SOL-USD", "close": 5.0}


def test_get_price_symbol_with_dash_used_as_is_uppercased(monkeypatch):
    pl = CryptoPlugin()
    seen = {}

    async def fake_fetch(symbol, start, end):
        seen["symbol"] = symbol
        return [(1, 7.0)]

    monkeypatch.setattr(pl, "_fetch_history", fake_fetch)
    out = asyncio.run(pl.get_price("btc-eur"))
    assert seen["symbol"] == "BTC-EUR"
    assert out == {"symbol": "BTC-EUR", "close": 7.0}


def test_get_price_uses_last_point_close_and_seven_day_window(monkeypatch):
    pl = CryptoPlugin()
    window = {}

    async def fake_fetch(symbol, start, end):
        window["start"] = start
        window["end"] = end
        return [(1, 10.0), (2, 20.0), (3, 30.0)]

    monkeypatch.setattr(pl, "_fetch_history", fake_fetch)
    out = asyncio.run(pl.get_price("BTC-USD"))
    assert out == {"symbol": "BTC-USD", "close": 30.0}
    assert (window["end"] - window["start"]).days == 7


def test_get_price_unavailable_when_fetch_returns_empty(monkeypatch):
    pl = CryptoPlugin()
    monkeypatch.setattr(pl, "_fetch_history", AsyncMock(return_value=[]))
    out = asyncio.run(pl.get_price("BTC-USD"))
    assert out == {"symbol": "BTC-USD", "error": "price unavailable"}
