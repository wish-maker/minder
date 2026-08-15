"""Unit tests for the TEFAS fund-price plugin (src/plugins/tefas).

Covers config parsing/apply_config, lifecycle, the blocking tefas-crawler
fetch-and-parse path (``_fetch_sync``/``_fetch_history``, no real network access,
no real tefas-crawler calls), the InfluxDB resume/write helpers (mocked httpx),
the crypto-style incremental collect_data date-branching, and the registry-driven
read/action surface.

Does NOT duplicate tests/unit/test_plugin_influx_symbol_validation.py (which locks
the ``_SAFE_CODE`` regex itself) -- instead verifies that ``_latest_influx_date``/
``_write_history`` actually consult it and short-circuit (no HTTP call) on an
unsafe fund code.
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

import plugins.tefas as tefasmod
from plugins.tefas import _DEFAULT_START, TefasPlugin


# ── httpx stand-ins (InfluxDB HTTP calls only) ───────────────────────────────
class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeAsyncClient:
    """Minimal async-context-manager httpx.AsyncClient stand-in."""

    def __init__(self, data=None, exc=None):
        self._data = data
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kwargs):
        if self._exc:
            raise self._exc
        return _FakeResponse(self._data)

    async def post(self, url, **kwargs):
        if self._exc:
            raise self._exc
        return _FakeResponse(self._data)


class _ExplodingClient:
    """Counts instantiations; used to assert "no HTTP call was made"."""

    calls = 0

    def __init__(self, *a, **kw):
        _ExplodingClient.calls += 1


# ── fake tefas-crawler DataFrame-like object ─────────────────────────────────
class _FakeDF:
    """Minimal stand-in for the pandas DataFrame ``Crawler().fetch(...)`` returns."""

    def __init__(self, rows):
        self._rows = rows

    def iterrows(self):
        for i, row in enumerate(self._rows):
            yield i, row


class _RaisingDF:
    def iterrows(self):
        raise RuntimeError("bad dataframe")


class _FakeCrawler:
    def __init__(self, df=None, exc=None):
        self._df = df
        self._exc = exc

    def fetch(self, **kwargs):
        if self._exc:
            raise self._exc
        return self._df


def _patch_crawler(monkeypatch, df=None, exc=None):
    monkeypatch.setattr(
        tefasmod, "Crawler", lambda: _FakeCrawler(df=df, exc=exc), raising=False
    )


_ENABLED_CFG = {
    "influxdb": {
        "enabled": True,
        "host": "h",
        "port": 1,
        "token": "t",
        "org": "o",
        "bucket": "b",
    }
}


# ── apply_config ─────────────────────────────────────────────────────────────
def test_apply_config_funds_comma_split_upper_blank_dropped():
    pl = TefasPlugin()
    pl.apply_config({"TEFAS_FUNDS": " afa , aak ,, IPB "})
    assert pl.funds == ["AFA", "AAK", "IPB"]


def test_apply_config_funds_default_empty():
    pl = TefasPlugin()
    pl.apply_config({"TEFAS_FUNDS": ""})
    assert pl.funds == []


def test_apply_config_start_date_passthrough():
    pl = TefasPlugin()
    pl.apply_config({"TEFAS_START_DATE": "2020-06-01"})
    assert pl.start_date == "2020-06-01"


def test_apply_config_start_date_blank_falls_back_to_default():
    pl = TefasPlugin()
    pl.apply_config({"TEFAS_START_DATE": ""})
    assert pl.start_date == _DEFAULT_START


def test_apply_config_sink_influxdb_truthy_strings():
    pl = TefasPlugin()
    for v in ("1", "true", "yes", "on", "TRUE", "On"):
        pl.apply_config({"TEFAS_SINK_INFLUXDB": v})
        assert pl.sink_influxdb is True
    for v in ("0", "false", "no", "", "off"):
        pl.apply_config({"TEFAS_SINK_INFLUXDB": v})
        assert pl.sink_influxdb is False


def test_apply_config_sink_influxdb_bool_passthrough():
    pl = TefasPlugin()
    pl.apply_config({"TEFAS_SINK_INFLUXDB": True})
    assert pl.sink_influxdb is True
    pl.apply_config({"TEFAS_SINK_INFLUXDB": False})
    assert pl.sink_influxdb is False


def test_init_defaults_from_env(monkeypatch):
    monkeypatch.delenv("TEFAS_FUNDS", raising=False)
    monkeypatch.delenv("TEFAS_START_DATE", raising=False)
    monkeypatch.delenv("TEFAS_SINK_INFLUXDB", raising=False)
    pl = TefasPlugin()
    assert pl.funds == []
    assert pl.start_date == _DEFAULT_START
    assert pl.sink_influxdb is True


# ── lifecycle ────────────────────────────────────────────────────────────────
def test_register_and_health():
    pl = TefasPlugin()
    pl.funds = ["AFA"]
    md = asyncio.run(pl.register())
    assert md.name == "tefas"
    h = asyncio.run(pl.health_check())
    assert h == {
        "healthy": True,
        "tefas_available": tefasmod.TEFAS_AVAILABLE,
        "funds": ["AFA"],
        "influxdb_sink": pl.sink_influxdb,
    }


def test_lifecycle_status_transitions():
    pl = TefasPlugin()
    assert pl.status == "registered"
    asyncio.run(pl.initialize())
    assert pl.status == "ready"
    asyncio.run(pl.shutdown())
    assert pl.status == "shutdown"


# ── _fetch_sync ───────────────────────────────────────────────────────────────
def test_fetch_sync_parses_date_object_rows_and_skips_none_price(monkeypatch):
    rows = [
        {"date": date(2024, 1, 1), "price": 10.5},
        {"date": date(2024, 1, 2), "price": None},
    ]
    _patch_crawler(monkeypatch, df=_FakeDF(rows))
    pl = TefasPlugin()
    out = pl._fetch_sync("AFA", date(2024, 1, 1), date(2024, 1, 2))
    expected_ts = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())
    assert out == [(expected_ts, 10.5)]


def test_fetch_sync_parses_datetime_row(monkeypatch):
    rows = [{"date": datetime(2024, 1, 4, 12, 30), "price": 7.0}]
    _patch_crawler(monkeypatch, df=_FakeDF(rows))
    pl = TefasPlugin()
    out = pl._fetch_sync("AFA", date(2024, 1, 1), date(2024, 1, 5))
    expected_ts = int(datetime(2024, 1, 4, tzinfo=timezone.utc).timestamp())
    assert out == [(expected_ts, 7.0)]


def test_fetch_sync_parses_iso_string_date_row(monkeypatch):
    rows = [{"date": "2024-01-03T00:00:00", "price": 5.0}]
    _patch_crawler(monkeypatch, df=_FakeDF(rows))
    pl = TefasPlugin()
    out = pl._fetch_sync("AFA", date(2024, 1, 1), date(2024, 1, 5))
    expected_ts = int(datetime(2024, 1, 3, tzinfo=timezone.utc).timestamp())
    assert out == [(expected_ts, 5.0)]


def test_fetch_sync_returns_empty_on_fetch_exception(monkeypatch):
    _patch_crawler(monkeypatch, exc=RuntimeError("blocked/robot-check"))
    pl = TefasPlugin()
    assert pl._fetch_sync("AFA", date(2024, 1, 1), date(2024, 1, 2)) == []


def test_fetch_sync_returns_empty_on_parse_exception(monkeypatch):
    _patch_crawler(monkeypatch, df=_RaisingDF())
    pl = TefasPlugin()
    assert pl._fetch_sync("AFA", date(2024, 1, 1), date(2024, 1, 2)) == []


# ── _fetch_history ────────────────────────────────────────────────────────────
def test_fetch_history_returns_empty_without_calling_fetch_sync_when_unavailable(
    monkeypatch,
):
    pl = TefasPlugin()
    monkeypatch.setattr(tefasmod, "TEFAS_AVAILABLE", False)

    def boom(*a, **kw):
        raise AssertionError("_fetch_sync should not be called")

    monkeypatch.setattr(pl, "_fetch_sync", boom)
    out = asyncio.run(pl._fetch_history("AFA", date(2024, 1, 1), date(2024, 1, 2)))
    assert out == []


def test_fetch_history_delegates_to_fetch_sync_via_to_thread(monkeypatch):
    pl = TefasPlugin()
    monkeypatch.setattr(tefasmod, "TEFAS_AVAILABLE", True)
    calls = []

    def fake_fetch_sync(code, start, end):
        calls.append((code, start, end))
        return [(123, 1.5)]

    monkeypatch.setattr(pl, "_fetch_sync", fake_fetch_sync)
    start, end = date(2024, 1, 1), date(2024, 1, 2)
    out = asyncio.run(pl._fetch_history("AFA", start, end))
    assert out == [(123, 1.5)]
    assert calls == [("AFA", start, end)]


# ── _influx_cfg ───────────────────────────────────────────────────────────────
def test_influx_cfg_none_when_sink_disabled():
    pl = TefasPlugin()
    pl.sink_influxdb = False
    pl.config = {"influxdb": {"enabled": True}}
    assert pl._influx_cfg() is None


def test_influx_cfg_none_when_influxdb_not_enabled():
    pl = TefasPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": False}}
    assert pl._influx_cfg() is None


def test_influx_cfg_returns_cfg_when_enabled():
    pl = TefasPlugin()
    pl.sink_influxdb = True
    pl.config = dict(_ENABLED_CFG)
    assert pl._influx_cfg() == _ENABLED_CFG["influxdb"]


# ── _latest_influx_date ───────────────────────────────────────────────────────
def test_latest_influx_date_none_when_cfg_none():
    pl = TefasPlugin()
    pl.sink_influxdb = False
    pl.config = {}
    assert asyncio.run(pl._latest_influx_date("AFA")) is None


def test_latest_influx_date_none_and_no_http_call_for_unsafe_code(monkeypatch):
    pl = TefasPlugin()
    pl.sink_influxdb = True
    pl.config = dict(_ENABLED_CFG)
    _ExplodingClient.calls = 0
    monkeypatch.setattr(tefasmod.httpx, "AsyncClient", _ExplodingClient)
    out = asyncio.run(pl._latest_influx_date("AFA'; DROP TABLE x --"))
    assert out is None
    assert _ExplodingClient.calls == 0


def test_latest_influx_date_parses_row_strips_trailing_z(monkeypatch):
    pl = TefasPlugin()
    pl.sink_influxdb = True
    pl.config = dict(_ENABLED_CFG)
    monkeypatch.setattr(
        tefasmod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(data=[{"t": "2024-03-15T00:00:00Z"}]),
    )
    out = asyncio.run(pl._latest_influx_date("AFA"))
    assert out == date(2024, 3, 15)


def test_latest_influx_date_none_when_rows_empty(monkeypatch):
    pl = TefasPlugin()
    pl.sink_influxdb = True
    pl.config = dict(_ENABLED_CFG)
    monkeypatch.setattr(
        tefasmod.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(data=[])
    )
    assert asyncio.run(pl._latest_influx_date("AFA")) is None


def test_latest_influx_date_none_when_t_falsy(monkeypatch):
    pl = TefasPlugin()
    pl.sink_influxdb = True
    pl.config = dict(_ENABLED_CFG)
    monkeypatch.setattr(
        tefasmod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(data=[{"t": None}]),
    )
    assert asyncio.run(pl._latest_influx_date("AFA")) is None


@pytest.mark.parametrize(
    "rows",
    [
        {"error": "query failed"},
        [["2024-01-15T00:00:00"]],
    ],
)
def test_latest_influx_date_none_on_malformed_response_shape(monkeypatch, rows):
    """Malformed shapes InfluxDB v3's query_sql could plausibly return on a
    200 (an error/status object instead of a bare row array, or rows encoded
    as arrays not objects) -- rows[0].get(...) with no shape check would raise
    OUTSIDE this function's own try/except, aborting every remaining fund in
    the caller's collection loop instead of just returning "no resume point"
    for this one."""
    pl = TefasPlugin()
    pl.sink_influxdb = True
    pl.config = dict(_ENABLED_CFG)
    monkeypatch.setattr(
        tefasmod.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(data=rows)
    )
    assert asyncio.run(pl._latest_influx_date("AFA")) is None


def test_latest_influx_date_none_on_http_exception_and_warns(monkeypatch, caplog):
    """Mirrors crypto's identical helper, which logs this failure -- tefas's
    version used to swallow it with a bare `except Exception: return None`,
    so a persistently-failing resume query (bad token, InfluxDB down) was
    invisible: every symbol looked like "no prior data," silently triggering
    a full history refetch every cycle forever, with nothing in the logs."""
    pl = TefasPlugin()
    pl.sink_influxdb = True
    pl.config = dict(_ENABLED_CFG)
    monkeypatch.setattr(
        tefasmod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(exc=RuntimeError("boom")),
    )
    with caplog.at_level("WARNING"):
        assert asyncio.run(pl._latest_influx_date("AFA")) is None
    assert any("resume query failed" in r.message for r in caplog.records)


def test_latest_influx_date_none_on_unparseable_date(monkeypatch):
    pl = TefasPlugin()
    pl.sink_influxdb = True
    pl.config = dict(_ENABLED_CFG)
    monkeypatch.setattr(
        tefasmod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(data=[{"t": "not-a-date"}]),
    )
    assert asyncio.run(pl._latest_influx_date("AFA")) is None


# ── _write_history ─────────────────────────────────────────────────────────────
def test_write_history_zero_when_cfg_none():
    pl = TefasPlugin()
    pl.sink_influxdb = False
    pl.config = {}
    assert asyncio.run(pl._write_history("AFA", [(1, 1.0)])) == 0


def test_write_history_zero_when_points_empty():
    pl = TefasPlugin()
    pl.sink_influxdb = True
    pl.config = dict(_ENABLED_CFG)
    assert asyncio.run(pl._write_history("AFA", [])) == 0


def test_write_history_zero_and_no_http_call_for_unsafe_code(monkeypatch):
    pl = TefasPlugin()
    pl.sink_influxdb = True
    pl.config = dict(_ENABLED_CFG)
    _ExplodingClient.calls = 0
    monkeypatch.setattr(tefasmod.httpx, "AsyncClient", _ExplodingClient)
    out = asyncio.run(pl._write_history("AFA'; DROP TABLE x --", [(1, 1.0)]))
    assert out == 0
    assert _ExplodingClient.calls == 0


def test_write_history_success_returns_point_count(monkeypatch):
    pl = TefasPlugin()
    pl.sink_influxdb = True
    pl.config = dict(_ENABLED_CFG)
    monkeypatch.setattr(
        tefasmod.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(data="")
    )
    out = asyncio.run(pl._write_history("AFA", [(1, 1.0), (2, 2.0)]))
    assert out == 2


def test_write_history_zero_on_http_exception(monkeypatch):
    pl = TefasPlugin()
    pl.sink_influxdb = True
    pl.config = dict(_ENABLED_CFG)
    monkeypatch.setattr(
        tefasmod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(exc=RuntimeError("boom")),
    )
    assert asyncio.run(pl._write_history("AFA", [(1, 1.0)])) == 0


# ── collect_data ──────────────────────────────────────────────────────────────
def test_collect_data_up_to_date_when_resume_point_past_today(monkeypatch):
    pl = TefasPlugin()
    pl.funds = ["AFA"]
    today = datetime.now(timezone.utc).date()
    monkeypatch.setattr(pl, "_latest_influx_date", AsyncMock(return_value=today))

    def boom(*a, **kw):
        raise AssertionError("_fetch_history should not be called")

    monkeypatch.setattr(pl, "_fetch_history", boom)
    result = asyncio.run(pl.collect_data())
    assert result["funds"]["AFA"] == {"written": 0, "up_to_date": True}


def test_collect_data_resumes_from_day_after_latest(monkeypatch):
    pl = TefasPlugin()
    pl.funds = ["AFA"]
    latest = datetime.now(timezone.utc).date() - timedelta(days=3)
    monkeypatch.setattr(pl, "_latest_influx_date", AsyncMock(return_value=latest))
    seen = {}

    async def fake_fetch(code, start, end):
        seen["start"] = start
        return [(1, 9.0)]

    monkeypatch.setattr(pl, "_fetch_history", fake_fetch)
    monkeypatch.setattr(pl, "_write_history", AsyncMock(return_value=1))
    result = asyncio.run(pl.collect_data())
    assert seen["start"] == latest + timedelta(days=1)
    assert result["funds"]["AFA"]["from"] == (latest + timedelta(days=1)).isoformat()
    assert result["funds"]["AFA"]["latest_price"] == 9.0


def test_collect_data_uses_configured_start_date_when_no_resume_point(monkeypatch):
    pl = TefasPlugin()
    pl.funds = ["AFA"]
    pl.start_date = "2020-01-01"
    monkeypatch.setattr(pl, "_latest_influx_date", AsyncMock(return_value=None))
    seen = {}

    async def fake_fetch(code, start, end):
        seen["start"] = start
        return []

    monkeypatch.setattr(pl, "_fetch_history", fake_fetch)
    monkeypatch.setattr(pl, "_write_history", AsyncMock(return_value=0))
    asyncio.run(pl.collect_data())
    assert seen["start"] == date(2020, 1, 1)


def test_collect_data_falls_back_to_default_start_when_unparseable(monkeypatch):
    pl = TefasPlugin()
    pl.funds = ["AFA"]
    pl.start_date = "not-a-date"
    monkeypatch.setattr(pl, "_latest_influx_date", AsyncMock(return_value=None))
    seen = {}

    async def fake_fetch(code, start, end):
        seen["start"] = start
        return []

    monkeypatch.setattr(pl, "_fetch_history", fake_fetch)
    monkeypatch.setattr(pl, "_write_history", AsyncMock(return_value=0))
    asyncio.run(pl.collect_data())
    assert seen["start"] == date.fromisoformat(_DEFAULT_START)


def test_collect_data_aggregates_across_funds_independently(monkeypatch):
    pl = TefasPlugin()
    pl.funds = ["AFA", "AAK"]
    monkeypatch.setattr(pl, "_latest_influx_date", AsyncMock(return_value=None))
    pl.start_date = "2024-01-01"

    fetch_results = {"AFA": [(1, 1.1)], "AAK": []}

    async def fake_fetch(code, start, end):
        return fetch_results[code]

    async def fake_write(code, points):
        return len(points)

    monkeypatch.setattr(pl, "_fetch_history", fake_fetch)
    monkeypatch.setattr(pl, "_write_history", fake_write)
    result = asyncio.run(pl.collect_data())
    assert result["funds"]["AFA"]["written"] == 1
    assert result["funds"]["AFA"]["latest_price"] == 1.1
    assert result["funds"]["AAK"]["written"] == 0
    assert result["funds"]["AAK"]["latest_price"] is None
    assert pl._last == result


# ── analyze / refresh ─────────────────────────────────────────────────────────
def test_analyze_before_any_collection():
    pl = TefasPlugin()
    pl.funds = ["AFA"]
    out = asyncio.run(pl.analyze())
    assert out == {"message": "no data collected yet", "funds": ["AFA"]}


def test_analyze_returns_last_collection(monkeypatch):
    pl = TefasPlugin()
    pl.funds = ["AFA"]
    monkeypatch.setattr(pl, "_latest_influx_date", AsyncMock(return_value=None))
    monkeypatch.setattr(pl, "_fetch_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(pl, "_write_history", AsyncMock(return_value=0))
    asyncio.run(pl.collect_data())
    assert asyncio.run(pl.analyze()) == pl._last


def test_refresh_delegates_to_collect_data(monkeypatch):
    pl = TefasPlugin()
    monkeypatch.setattr(pl, "collect_data", AsyncMock(return_value={"ok": True}))
    assert asyncio.run(pl.refresh()) == {"ok": True}


# ── get_fund_price ─────────────────────────────────────────────────────────────
def test_get_fund_price_empty_code_is_error():
    pl = TefasPlugin()
    out = asyncio.run(pl.get_fund_price(""))
    assert out == {"error": "code is required"}


def test_get_fund_price_strips_and_upper_cases_code(monkeypatch):
    pl = TefasPlugin()
    seen = {}

    async def fake_fetch(code, start, end):
        seen["code"] = code
        seen["start"] = start
        seen["end"] = end
        return [(1, 3.0)]

    monkeypatch.setattr(pl, "_fetch_history", fake_fetch)
    out = asyncio.run(pl.get_fund_price("  afa  "))
    assert seen["code"] == "AFA"
    today = datetime.now(timezone.utc).date()
    assert seen["start"] == today - timedelta(days=10)
    assert seen["end"] == today
    assert out == {"code": "AFA", "price": 3.0}


def test_get_fund_price_no_points_is_error(monkeypatch):
    pl = TefasPlugin()
    monkeypatch.setattr(pl, "_fetch_history", AsyncMock(return_value=[]))
    out = asyncio.run(pl.get_fund_price("AFA"))
    assert out == {"code": "AFA", "error": "price unavailable"}


def test_get_fund_price_returns_last_point_price(monkeypatch):
    pl = TefasPlugin()
    monkeypatch.setattr(
        pl, "_fetch_history", AsyncMock(return_value=[(1, 1.0), (2, 2.5)])
    )
    out = asyncio.run(pl.get_fund_price("AFA"))
    assert out == {"code": "AFA", "price": 2.5}
