"""Unit tests for the weather plugin (src/plugins/weather).

Covers _parse_locations/apply_config, the current-conditions + geocoding fetch
paths (mocked httpx, no real network access), the InfluxDB sink, and the
registry-driven read/action surface.
"""

import asyncio
from unittest.mock import AsyncMock

import plugins.weather as weathermod
from plugins.weather import WeatherPlugin


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data

    def raise_for_status(self):
        pass


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


# ── _parse_locations ─────────────────────────────────────────────────────────
def test_parse_locations_valid_triples():
    out = WeatherPlugin._parse_locations("Istanbul:41.01:28.98,London:51.51:-0.13")
    assert out == [("Istanbul", 41.01, 28.98), ("London", 51.51, -0.13)]


def test_parse_locations_skips_wrong_part_count():
    out = WeatherPlugin._parse_locations("Istanbul:41.01:28.98,justname,a:b:c:d")
    assert out == [("Istanbul", 41.01, 28.98)]


def test_parse_locations_skips_non_numeric_lat_lon():
    out = WeatherPlugin._parse_locations("Bad:notanumber:28.98,Istanbul:41.01:28.98")
    assert out == [("Istanbul", 41.01, 28.98)]


def test_parse_locations_empty_spec():
    assert WeatherPlugin._parse_locations("") == []


# ── apply_config / __init__ ──────────────────────────────────────────────────
def test_apply_config_maps_all_keys():
    pl = WeatherPlugin()
    pl.apply_config(
        {
            "WEATHER_LOCATIONS": "Tokyo:35.68:139.69",
            "WEATHER_SINK_INFLUXDB": False,
        }
    )
    assert pl.locations == [("Tokyo", 35.68, 139.69)]
    assert pl.sink_influxdb is False


def test_apply_config_sink_influxdb_string_truthy_values():
    pl = WeatherPlugin()
    for v in ("1", "true", "yes", "on", "TRUE"):
        pl.apply_config({"WEATHER_SINK_INFLUXDB": v})
        assert pl.sink_influxdb is True
    for v in ("0", "false", "no", ""):
        pl.apply_config({"WEATHER_SINK_INFLUXDB": v})
        assert pl.sink_influxdb is False


def test_apply_config_sink_influxdb_bool_passthrough():
    pl = WeatherPlugin()
    pl.apply_config({"WEATHER_SINK_INFLUXDB": True})
    assert pl.sink_influxdb is True
    pl.apply_config({"WEATHER_SINK_INFLUXDB": False})
    assert pl.sink_influxdb is False


def test_init_default_locations_bootstrap():
    pl = WeatherPlugin()
    assert pl.locations == [("Istanbul", 41.01, 28.98), ("London", 51.51, -0.13)]
    assert pl.sink_influxdb is True


# ── lifecycle ────────────────────────────────────────────────────────────────
def test_register_and_health():
    pl = WeatherPlugin()
    md = asyncio.run(pl.register())
    assert md.name == "weather"
    h = asyncio.run(pl.health_check())
    assert h["healthy"] is True
    assert set(h["locations"]) == {n for n, _, _ in pl.locations}
    assert h["influxdb_sink"] == pl.sink_influxdb


def test_lifecycle_status_transitions():
    pl = WeatherPlugin()
    assert pl.status == "registered"
    asyncio.run(pl.initialize())
    assert pl.status == "ready"
    asyncio.run(pl.shutdown())
    assert pl.status == "shutdown"


# ── _fetch_current ───────────────────────────────────────────────────────────
def test_fetch_current_success(monkeypatch):
    monkeypatch.setattr(
        weathermod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(
            data={
                "current": {
                    "temperature_2m": 21.5,
                    "relative_humidity_2m": 60,
                    "wind_speed_10m": 10.2,
                }
            }
        ),
    )
    pl = WeatherPlugin()
    r = asyncio.run(pl._fetch_current(41.01, 28.98))
    assert r == {"temperature": 21.5, "humidity": 60, "wind_speed": 10.2}


def test_fetch_current_returns_none_on_exception(monkeypatch):
    monkeypatch.setattr(
        weathermod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(exc=RuntimeError("boom")),
    )
    pl = WeatherPlugin()
    assert asyncio.run(pl._fetch_current(41.01, 28.98)) is None


def test_fetch_current_missing_current_key_returns_none_fields(monkeypatch):
    monkeypatch.setattr(
        weathermod.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(data={})
    )
    pl = WeatherPlugin()
    r = asyncio.run(pl._fetch_current(41.01, 28.98))
    assert r == {"temperature": None, "humidity": None, "wind_speed": None}


# ── _geocode ─────────────────────────────────────────────────────────────────
def test_geocode_success(monkeypatch):
    monkeypatch.setattr(
        weathermod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(
            data={"results": [{"latitude": 35.68, "longitude": 139.69}]}
        ),
    )
    pl = WeatherPlugin()
    assert asyncio.run(pl._geocode("Tokyo")) == (35.68, 139.69)


def test_geocode_empty_results_returns_none(monkeypatch):
    monkeypatch.setattr(
        weathermod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(data={"results": []}),
    )
    pl = WeatherPlugin()
    assert asyncio.run(pl._geocode("Nowhereville")) is None


def test_geocode_non_dict_result_returns_none(monkeypatch):
    """An ambiguous/administrative-only match (or any future API change) could
    return a results[0] that isn't a dict -- results[0].get(...) with no shape
    check would raise OUTSIDE the try/except above instead of the graceful
    None this fail-soft function is meant to return."""
    monkeypatch.setattr(
        weathermod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(data={"results": ["not-a-dict"]}),
    )
    pl = WeatherPlugin()
    assert asyncio.run(pl._geocode("Ambiguous Place")) is None


def test_geocode_returns_none_on_exception(monkeypatch):
    monkeypatch.setattr(
        weathermod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(exc=RuntimeError("boom")),
    )
    pl = WeatherPlugin()
    assert asyncio.run(pl._geocode("Tokyo")) is None


# ── _write_influxdb ──────────────────────────────────────────────────────────
def test_write_influxdb_noop_when_sink_disabled():
    pl = WeatherPlugin()
    pl.sink_influxdb = False
    pl.config = {"influxdb": {"enabled": True}}
    readings = {"Istanbul": {"temperature": 20, "humidity": 50, "wind_speed": 5}}
    assert asyncio.run(pl._write_influxdb(readings)) is False


def test_write_influxdb_noop_when_influxdb_not_enabled():
    pl = WeatherPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": False}}
    readings = {"Istanbul": {"temperature": 20, "humidity": 50, "wind_speed": 5}}
    assert asyncio.run(pl._write_influxdb(readings)) is False


def test_write_influxdb_noop_when_readings_empty():
    pl = WeatherPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": True}}
    assert asyncio.run(pl._write_influxdb({})) is False


def test_write_influxdb_noop_when_no_numeric_fields():
    pl = WeatherPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": True}}
    readings = {"Istanbul": {"temperature": None, "humidity": None, "wind_speed": None}}
    assert asyncio.run(pl._write_influxdb(readings)) is False


def test_write_influxdb_success(monkeypatch):
    pl = WeatherPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": True, "host": "h", "port": 1, "token": "t"}}
    monkeypatch.setattr(
        weathermod.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(data={})
    )
    readings = {"Istanbul": {"temperature": 20, "humidity": 50, "wind_speed": 5}}
    assert asyncio.run(pl._write_influxdb(readings)) is True


def test_write_influxdb_failure_returns_false(monkeypatch):
    pl = WeatherPlugin()
    pl.sink_influxdb = True
    pl.config = {"influxdb": {"enabled": True}}
    monkeypatch.setattr(
        weathermod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(exc=RuntimeError("boom")),
    )
    readings = {"Istanbul": {"temperature": 20, "humidity": 50, "wind_speed": 5}}
    assert asyncio.run(pl._write_influxdb(readings)) is False


# ── collect_data / analyze / refresh ─────────────────────────────────────────
def test_collect_data_aggregates_across_locations(monkeypatch):
    pl = WeatherPlugin()
    pl.locations = [("A", 1.0, 1.0), ("B", 2.0, 2.0)]

    async def fake_fetch(lat, lon):
        return {"temperature": lat, "humidity": 50, "wind_speed": 5}

    monkeypatch.setattr(pl, "_fetch_current", fake_fetch)
    monkeypatch.setattr(pl, "_write_influxdb", AsyncMock(return_value=False))
    result = asyncio.run(pl.collect_data())
    assert result["readings"] == {
        "A": {"temperature": 1.0, "humidity": 50, "wind_speed": 5},
        "B": {"temperature": 2.0, "humidity": 50, "wind_speed": 5},
    }
    assert result["influxdb_written"] is False
    assert pl._last == result


def test_collect_data_skips_locations_with_none_fetch(monkeypatch):
    pl = WeatherPlugin()
    pl.locations = [("Good", 1.0, 1.0), ("Bad", 2.0, 2.0)]

    async def fake_fetch(lat, lon):
        return (
            None if lat == 2.0 else {"temperature": 1, "humidity": 1, "wind_speed": 1}
        )

    monkeypatch.setattr(pl, "_fetch_current", fake_fetch)
    monkeypatch.setattr(pl, "_write_influxdb", AsyncMock(return_value=False))
    result = asyncio.run(pl.collect_data())
    assert list(result["readings"].keys()) == ["Good"]


def test_collect_data_calls_write_influxdb(monkeypatch):
    pl = WeatherPlugin()
    pl.locations = [("A", 1.0, 1.0)]
    monkeypatch.setattr(
        pl,
        "_fetch_current",
        AsyncMock(return_value={"temperature": 1, "humidity": 1, "wind_speed": 1}),
    )
    write_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(pl, "_write_influxdb", write_mock)
    result = asyncio.run(pl.collect_data())
    write_mock.assert_awaited_once_with(result["readings"])
    assert result["influxdb_written"] is True


def test_analyze_before_any_collection():
    pl = WeatherPlugin()
    out = asyncio.run(pl.analyze())
    assert out["message"] == "no data collected yet"
    assert set(out["locations"]) == {n for n, _, _ in pl.locations}


def test_analyze_returns_last_collection(monkeypatch):
    pl = WeatherPlugin()
    pl.locations = [("A", 1.0, 1.0)]
    monkeypatch.setattr(
        pl,
        "_fetch_current",
        AsyncMock(return_value={"temperature": 1, "humidity": 1, "wind_speed": 1}),
    )
    monkeypatch.setattr(pl, "_write_influxdb", AsyncMock(return_value=False))
    asyncio.run(pl.collect_data())
    assert asyncio.run(pl.analyze()) == pl._last


def test_refresh_calls_collect_data(monkeypatch):
    pl = WeatherPlugin()
    monkeypatch.setattr(pl, "collect_data", AsyncMock(return_value={"ok": True}))
    assert asyncio.run(pl.refresh()) == {"ok": True}


# ── get_weather ──────────────────────────────────────────────────────────────
def test_get_weather_empty_location():
    pl = WeatherPlugin()
    out = asyncio.run(pl.get_weather(""))
    assert out == {"error": "location is required"}


def test_get_weather_geocode_none_returns_error(monkeypatch):
    pl = WeatherPlugin()
    monkeypatch.setattr(pl, "_geocode", AsyncMock(return_value=None))
    out = asyncio.run(pl.get_weather("Nowhereville"))
    assert out == {"location": "Nowhereville", "error": "could not resolve location"}


def test_get_weather_geocode_lat_none_returns_error(monkeypatch):
    pl = WeatherPlugin()
    monkeypatch.setattr(pl, "_geocode", AsyncMock(return_value=(None, 1.0)))
    out = asyncio.run(pl.get_weather("Nowhereville"))
    assert out == {"location": "Nowhereville", "error": "could not resolve location"}


def test_get_weather_fetch_none_returns_error(monkeypatch):
    pl = WeatherPlugin()
    monkeypatch.setattr(pl, "_geocode", AsyncMock(return_value=(35.68, 139.69)))
    monkeypatch.setattr(pl, "_fetch_current", AsyncMock(return_value=None))
    out = asyncio.run(pl.get_weather("Tokyo"))
    assert out == {"location": "Tokyo", "error": "weather unavailable"}


def test_get_weather_success(monkeypatch):
    pl = WeatherPlugin()
    monkeypatch.setattr(pl, "_geocode", AsyncMock(return_value=(35.68, 139.69)))
    monkeypatch.setattr(
        pl,
        "_fetch_current",
        AsyncMock(return_value={"temperature": 30, "humidity": 40, "wind_speed": 3}),
    )
    out = asyncio.run(pl.get_weather("Tokyo"))
    assert out == {
        "location": "Tokyo",
        "temperature": 30,
        "humidity": 40,
        "wind_speed": 3,
    }
